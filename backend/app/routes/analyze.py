"""
Analyze route module.

Handles R&D proposal analysis requests using the local Ollama LLM.

POST /api/analyze — upload PDF → extract text → run orchestrator pipeline
                    (general_analysis + coordinator) → return full result

POST /api/analyze/text — re-analyze already-extracted text (no PDF needed)
"""
from fastapi import APIRouter, File, UploadFile, HTTPException, status
from pydantic import BaseModel
from typing import Optional

from app.services.pdf_service import (
    PDFProcessingError,
    validate_pdf_upload,
    extract_text_from_pdf,
)
from app.services.orchestrator import run_full_evaluation
from app.services.llm_client import LLMClientError

router = APIRouter(prefix="/api", tags=["Analysis"])


class TextAnalysisRequest(BaseModel):
    """Payload for analyzing already extracted proposal text."""
    text:     str
    filename: Optional[str] = "Proposal Document"


@router.post(
    "/analyze",
    status_code=status.HTTP_200_OK,
    summary="Upload PDF, extract text, run full evaluation pipeline",
    description=(
        "Uploads an R&D proposal PDF, extracts text in memory, runs "
        "the general analysis agent and the coordinator agent, and returns "
        "a structured evaluation including a preliminary recommendation."
    ),
)
async def analyze_proposal_pdf(file: UploadFile = File(None)):
    """
    End-to-end endpoint:
    1. Validate and read the uploaded PDF in memory.
    2. Extract text page-by-page with PyMuPDF.
    3. Run orchestrator: general_analysis → coordinator.
    4. Return the full result dict merged with document metadata.
    """
    if file is None or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file selected. Please select an R&D proposal PDF file to analyze.",
        )

    try:
        file_bytes = await file.read()

        # Step 1: Validate
        validate_pdf_upload(
            filename=file.filename,
            content_type=file.content_type or "",
            file_bytes=file_bytes,
        )

        # Step 2: Extract text
        extraction = extract_text_from_pdf(
            filename=file.filename,
            file_bytes=file_bytes,
        )

        # Step 3: Run full evaluation pipeline
        pipeline_result = run_full_evaluation(
            proposal_text=extraction["full_text"],
            filename=file.filename,
        )

        # Step 4: Merge document metadata into response
        return {
            "filename":   file.filename,
            "page_count": extraction["page_count"],
            "char_count": extraction["char_count"],
            "pages":      extraction["pages"],
            "full_text":  extraction["full_text"],
            # analysis sub-dict (general_analysis result)
            "analysis":   pipeline_result["analysis"],
            # coordinator synthesis (None if coordinator failed)
            "coordinator":       pipeline_result.get("coordinator"),
            "coordinator_error": pipeline_result.get("coordinator_error"),
            "_agent_statuses":   pipeline_result.get("_agent_statuses", {}),
        }

    except PDFProcessingError as pdf_err:
        raise HTTPException(
            status_code=pdf_err.status_code,
            detail=pdf_err.message,
        ) from pdf_err

    except LLMClientError as llm_err:
        raise HTTPException(
            status_code=llm_err.status_code,
            detail=llm_err.message,
        ) from llm_err

    except HTTPException:
        raise

    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during proposal analysis: {str(err)}",
        ) from err

    finally:
        await file.close()


@router.post(
    "/analyze/text",
    status_code=status.HTTP_200_OK,
    summary="Run full evaluation pipeline on extracted text",
    description="Analyzes already-extracted proposal text without re-uploading a PDF.",
)
def analyze_extracted_text(request: TextAnalysisRequest):
    if not request.text or not request.text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Proposal text is empty. Please provide valid text to analyze.",
        )

    try:
        pipeline_result = run_full_evaluation(
            proposal_text=request.text,
            filename=request.filename or "Proposal Document",
        )
        return {
            "filename":          request.filename,
            "analysis":          pipeline_result["analysis"],
            "coordinator":       pipeline_result.get("coordinator"),
            "coordinator_error": pipeline_result.get("coordinator_error"),
            "_agent_statuses":   pipeline_result.get("_agent_statuses", {}),
        }
    except LLMClientError as llm_err:
        raise HTTPException(
            status_code=llm_err.status_code,
            detail=llm_err.message,
        ) from llm_err
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze proposal text: {str(err)}",
        ) from err
