"""
Evaluations route module.

POST /api/evaluations                      — save a completed analysis result
GET  /api/evaluations                      — list all saved evaluations
GET  /api/evaluations/{id}                 — fetch one full record
GET  /api/evaluations/{id}/report.pdf      — download PDF report (reportlab)
GET  /api/evaluations/{id}/export.json     — download raw evaluation JSON
GET  /api/analytics                        — aggregate statistics from the DB
"""
import json as _json

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from typing import Any, Dict, Optional

from app.services.database import (
    save_evaluation,
    get_evaluations,
    get_evaluation_by_id,
    compute_analytics,
)
from app.services.report_generator import generate_pdf_report

router = APIRouter(prefix="/api", tags=["Evaluations"])


# ── Request model for POST /api/evaluations ────────────────────────────────────

class EvaluationPayload(BaseModel):
    filename:    str
    page_count:  int
    char_count:  int
    model_used:  Optional[str]           = "unknown"
    analysis:    Dict[str, Any]
    full_result: Optional[Dict[str, Any]] = None
    # Coordinator fields — absent on evaluations from before Brick 7
    coordinator_summary:         Optional[Dict[str, Any]] = None
    preliminary_recommendation:  Optional[str]            = None
    recommendation_reasoning:    Optional[str]            = None


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post(
    "/evaluations",
    status_code=status.HTTP_201_CREATED,
    summary="Save a completed evaluation to the database",
)
def create_evaluation(payload: EvaluationPayload):
    try:
        record_id = save_evaluation(
            filename                    = payload.filename,
            analysis                    = payload.analysis,
            page_count                  = payload.page_count,
            char_count                  = payload.char_count,
            model_used                  = payload.model_used or "unknown",
            full_result                 = payload.full_result or {},
            coordinator_summary         = payload.coordinator_summary,
            preliminary_recommendation  = payload.preliminary_recommendation,
            recommendation_reasoning    = payload.recommendation_reasoning,
        )
        return {"status": "saved", "id": record_id, "filename": payload.filename}
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Failed to save evaluation: {err}") from err


@router.get(
    "/evaluations",
    summary="List all saved evaluations, newest first",
)
def list_evaluations(limit: int = 200):
    try:
        rows = get_evaluations(limit=limit)
        return {"evaluations": rows, "count": len(rows)}
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve evaluations: {err}") from err


@router.get(
    "/evaluations/{record_id}/report.pdf",
    summary="Download a PDF evaluation report",
    response_class=Response,
)
def download_pdf_report(record_id: str):
    """
    Generates and streams a PDF report for one evaluation record using reportlab.
    The filename in the Content-Disposition header is derived from the original PDF name.
    """
    row = get_evaluation_by_id(record_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Evaluation '{record_id}' not found.")

    try:
        pdf_bytes = generate_pdf_report(row)
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {err}") from err

    # Build a safe filename: strip extension, append -report.pdf
    base = row.get("filename", "evaluation")
    if base.lower().endswith(".pdf"):
        base = base[:-4]
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in base).strip() or "evaluation"
    dl_filename = f"{safe_name}-report.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{dl_filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


@router.get(
    "/evaluations/{record_id}/export.json",
    summary="Download raw evaluation JSON",
    response_class=Response,
)
def export_evaluation_json(record_id: str):
    """
    Returns the full evaluation record (including stored result_json) as a
    downloadable JSON file. Useful for archiving, debugging, or feeding into
    external tools.
    """
    row = get_evaluation_by_id(record_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Evaluation '{record_id}' not found.")

    base = row.get("filename", "evaluation")
    if base.lower().endswith(".pdf"):
        base = base[:-4]
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in base).strip() or "evaluation"
    dl_filename = f"{safe_name}-evaluation.json"

    json_bytes = _json.dumps(row, indent=2, ensure_ascii=False, default=str).encode("utf-8")

    return Response(
        content=json_bytes,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{dl_filename}"',
            "Content-Length": str(len(json_bytes)),
        },
    )


@router.get(
    "/evaluations/{record_id}",
    summary="Fetch a single evaluation record by ID",
)
def fetch_evaluation(record_id: str):
    row = get_evaluation_by_id(record_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Evaluation '{record_id}' not found.")
    return row


@router.get(
    "/analytics",
    summary="Aggregate analytics computed from saved evaluations",
)
def get_analytics():
    try:
        return compute_analytics()
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Failed to compute analytics: {err}") from err
