"""
orchestrator.py — Evaluation pipeline.

Brick 8 update:
  After general_analysis completes, scoring.py computes the weighted
  overall_score and score_band in pure Python.  The coordinator then
  receives the computed scores + band so it can reference and explain
  them rather than invent its own numeric assessment.

Pipeline:
  1. general_analysis   → analysis dict (includes score + justification)
  2. scoring.py         → ScoringResult (overall_score, score_band, …)
  3. coordinator_agent  → synthesis dict (references computed band)
"""
import logging
from typing import Any, Dict, Optional

from app.services.general_analysis import analyze_proposal, AGENT_NAME as GA_NAME
from app.services.scoring import compute_scores, scoring_result_to_dict
from app.agents.coordinator_agent import run_coordinator
from app.services.llm_client import LLMClientError

logger = logging.getLogger(__name__)


def run_full_evaluation(
    proposal_text: str,
    filename:      str,
    model:         Optional[str]  = None,
    timeout:       Optional[float] = None,
) -> Dict[str, Any]:
    """
    Run the complete evaluation pipeline.

    Returns a dict with:
        analysis          — general_analysis result (score, justification, …)
        scoring           — ScoringResult as dict (overall_score, score_band, …)
        coordinator       — coordinator synthesis, or None on failure
        coordinator_error — str if coordinator failed, else absent
        _agent_statuses   — {agent_name: "completed"|"failed"}
    """
    agent_statuses: Dict[str, str] = {}

    # ── Stage 1: General analysis ─────────────────────────────────────────────
    try:
        analysis = analyze_proposal(proposal_text)
        analysis_for_coord = {**analysis, "_status": "completed"}
        agent_statuses[GA_NAME] = "completed"
    except LLMClientError:
        raise
    except Exception as exc:
        raise RuntimeError(f"general_analysis stage failed: {exc}") from exc

    # ── Stage 2: Scoring (pure Python — no LLM) ───────────────────────────────
    # Only general_analysis provides a score in Brick 8.
    # technical / financial / impact are None until their agents are built.
    scoring_result = compute_scores(
        novelty   = analysis.get("score"),    # from general_analysis
        technical = None,
        financial = None,
        impact    = None,
    )
    scoring_dict = scoring_result_to_dict(scoring_result)

    # ── Stage 3: Coordinator synthesis ───────────────────────────────────────
    title = analysis.get("title_or_topic") or filename

    coordinator_result: Optional[Dict[str, Any]] = None
    coordinator_error:  Optional[str]  = None

    try:
        coordinator_result = run_coordinator(
            title        = title,
            agent_results = {GA_NAME: analysis_for_coord},
            scores        = scoring_dict,          # NEW — computed scores passed in
            model         = model,
            timeout       = timeout,
        )

        if "coordinator_error" in coordinator_result:
            coordinator_error  = coordinator_result.get("coordinator_error", "JSON parsing failed")
            coordinator_result = None
            agent_statuses["coordinator"] = "failed"
        else:
            agent_statuses["coordinator"] = "completed"

    except LLMClientError as llm_err:
        coordinator_error = str(llm_err)
        agent_statuses["coordinator"] = "failed"
        logger.warning("Coordinator LLMClientError: %s", coordinator_error)

    except Exception as exc:
        coordinator_error = f"Unexpected coordinator error: {exc}"
        agent_statuses["coordinator"] = "failed"
        logger.exception("Coordinator unexpected failure")

    result: Dict[str, Any] = {
        "analysis":        analysis,
        "scoring":         scoring_dict,
        "coordinator":     coordinator_result,
        "_agent_statuses": agent_statuses,
    }
    if coordinator_error:
        result["coordinator_error"] = coordinator_error

    return result
