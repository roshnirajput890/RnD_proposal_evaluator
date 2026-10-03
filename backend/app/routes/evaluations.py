"""
Evaluations route module — Brick 8.

POST /api/evaluations                      — save evaluation (now includes scores)
GET  /api/evaluations                      — list all saved evaluations
GET  /api/evaluations/{id}                 — fetch one full record
GET  /api/evaluations/{id}/report.pdf      — download PDF report
GET  /api/evaluations/{id}/export.json     — download raw JSON
POST /api/evaluations/{id}/review          — save reviewer override (never touches AI scores)
GET  /api/analytics                        — aggregate statistics
"""
import json as _json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, validator
from typing import Any, Dict, List, Optional

from app.services.database import (
    save_evaluation,
    save_reviewer_override,
    get_evaluations,
    get_evaluation_by_id,
    compute_analytics,
)
from app.services.report_generator import generate_pdf_report

router = APIRouter(prefix="/api", tags=["Evaluations"])


# ── Request models ─────────────────────────────────────────────────────────────

class EvaluationPayload(BaseModel):
    filename:    str
    page_count:  int
    char_count:  int
    model_used:  Optional[str]            = "unknown"
    analysis:    Dict[str, Any]
    full_result: Optional[Dict[str, Any]] = None
    # Brick 7
    coordinator_summary:         Optional[Dict[str, Any]] = None
    preliminary_recommendation:  Optional[str]            = None
    recommendation_reasoning:    Optional[str]            = None
    # Brick 8 — scores from scoring.py (via orchestrator)
    novelty_score:   Optional[int]   = None
    technical_score: Optional[int]   = None
    financial_score: Optional[int]   = None
    impact_score:    Optional[int]   = None
    overall_score:   Optional[float] = None
    score_band:      Optional[str]   = None


class ReviewerOverrideScore(BaseModel):
    """Override score for one dimension, with a mandatory comment."""
    score:   int = Field(..., ge=1, le=5)
    comment: str = Field(..., min_length=1)


class ReviewPayload(BaseModel):
    """
    Reviewer override payload.
    AI scores are NEVER touched — only reviewer_* columns are updated.
    """
    # Per-dimension reviewer scores (all optional — reviewer may override some or all)
    overrides: Optional[Dict[str, ReviewerOverrideScore]] = None   # e.g. {"novelty": {score,comment}}
    final_decision: Optional[str] = None    # "Approve" | "Revise" | "Reject"
    notes: Optional[str]          = None

    @validator("final_decision")
    def validate_decision(cls, v):
        if v is not None and v not in {"Approve", "Revise", "Reject"}:
            raise ValueError("final_decision must be 'Approve', 'Revise', or 'Reject'")
        return v


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/evaluations", status_code=status.HTTP_201_CREATED,
             summary="Save a completed evaluation")
def create_evaluation(payload: EvaluationPayload):
    try:
        record_id = save_evaluation(
            filename                   = payload.filename,
            analysis                   = payload.analysis,
            page_count                 = payload.page_count,
            char_count                 = payload.char_count,
            model_used                 = payload.model_used or "unknown",
            full_result                = payload.full_result or {},
            coordinator_summary        = payload.coordinator_summary,
            preliminary_recommendation = payload.preliminary_recommendation,
            recommendation_reasoning   = payload.recommendation_reasoning,
            novelty_score              = payload.novelty_score,
            technical_score            = payload.technical_score,
            financial_score            = payload.financial_score,
            impact_score               = payload.impact_score,
            overall_score              = payload.overall_score,
            score_band                 = payload.score_band,
        )
        return {"status": "saved", "id": record_id, "filename": payload.filename}
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Failed to save evaluation: {err}") from err


@router.get("/evaluations", summary="List all saved evaluations, newest first")
def list_evaluations(limit: int = 200):
    try:
        rows = get_evaluations(limit=limit)
        return {"evaluations": rows, "count": len(rows)}
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve evaluations: {err}") from err


@router.post("/evaluations/{record_id}/review", status_code=status.HTTP_200_OK,
             summary="Save reviewer override — AI scores are never modified")
def save_review(record_id: str, payload: ReviewPayload):
    """
    Updates only reviewer_overrides, reviewer_final_decision, reviewer_notes,
    and reviewer_updated_at.  The original AI scores are untouched.
    """
    row = get_evaluation_by_id(record_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Evaluation '{record_id}' not found.")

    overrides_dict = None
    if payload.overrides:
        overrides_dict = {
            dim: {"score": v.score, "comment": v.comment}
            for dim, v in payload.overrides.items()
        }

    updated = save_reviewer_override(
        record_id,
        reviewer_overrides      = overrides_dict,
        reviewer_final_decision = payload.final_decision,
        reviewer_notes          = payload.notes,
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"Evaluation '{record_id}' not found.")

    return {
        "status":    "review saved",
        "id":        record_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/evaluations/{record_id}/report.pdf",
            summary="Download PDF report", response_class=Response)
def download_pdf_report(record_id: str):
    row = get_evaluation_by_id(record_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Evaluation '{record_id}' not found.")
    try:
        pdf_bytes = generate_pdf_report(row)
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {err}") from err

    base = row.get("filename", "evaluation").removesuffix(".pdf")
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in base).strip() or "evaluation"
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe}-report.pdf"',
                 "Content-Length": str(len(pdf_bytes))},
    )


@router.get("/evaluations/{record_id}/export.json",
            summary="Download raw evaluation JSON", response_class=Response)
def export_evaluation_json(record_id: str):
    row = get_evaluation_by_id(record_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Evaluation '{record_id}' not found.")
    base = row.get("filename", "evaluation").removesuffix(".pdf")
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in base).strip() or "evaluation"
    json_bytes = _json.dumps(row, indent=2, ensure_ascii=False, default=str).encode("utf-8")
    return Response(
        content=json_bytes, media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{safe}-evaluation.json"',
                 "Content-Length": str(len(json_bytes))},
    )


@router.get("/evaluations/{record_id}", summary="Fetch a single evaluation record")
def fetch_evaluation(record_id: str):
    row = get_evaluation_by_id(record_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Evaluation '{record_id}' not found.")
    return row


@router.get("/analytics", summary="Aggregate analytics from saved evaluations")
def get_analytics():
    try:
        return compute_analytics()
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Failed to compute analytics: {err}") from err
