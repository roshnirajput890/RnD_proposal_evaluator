"""
Upload route module.

Handles multipart PDF file upload requests, delegates validation and extraction
to pdf_service, and returns structured page-by-page text extraction results.
"""
from fastapi import APIRouter, File, UploadFile, HTTPException, status
from app.services.pdf_service import (
    PDFProcessingError,
    validate_pdf_upload,
    extract_text_from_pdf,
)

# Initialize router with '/api' prefix
router = APIRouter(prefix="/api", tags=["Proposals"])


@router.post(
    "/upload",
    status_code=status.HTTP_200_OK,
    summary="Upload and extract text from an R&D Proposal PDF",
    description="Accepts a multipart/form-data PDF file, extracts text page-by-page in memory, and returns full text with page breakdown.",
)
async def upload_proposal_pdf(file: UploadFile = File(None)):
    """
    Endpoint to upload and extract text from an R&D proposal PDF.

    Args:
        file: Multipart file object.

    Returns:
        JSON response with filename, page_count, char_count, pages, and full_text.
    """
    # 1. Check if a file was provided in the request
    if file is None or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file selected. Please select an R&D proposal PDF file to upload.",
        )

    try:
        # 2. Read file content strictly in memory (no disk I/O)
        file_bytes = await file.read()

        # 3. Perform file type, header, and size validation
        validate_pdf_upload(
            filename=file.filename,
            content_type=file.content_type or "",
            file_bytes=file_bytes,
        )

        # 4. Extract text page-by-page using PyMuPDF (fitz)
        extraction_result = extract_text_from_pdf(
            filename=file.filename,
            file_bytes=file_bytes,
        )

        return extraction_result

    except PDFProcessingError as proc_err:
        # Known client-correctable validation or extraction error
        raise HTTPException(
            status_code=proc_err.status_code,
            detail=proc_err.message,
        ) from proc_err

    except HTTPException:
        # Re-raise explicit HTTP exceptions
        raise

    except Exception as unexpected_err:
        # Catch any unforeseen internal errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected server failure occurred: {str(unexpected_err)}",
        ) from unexpected_err

    finally:
        # Ensure the uploaded file stream handle is closed
        await file.close()
