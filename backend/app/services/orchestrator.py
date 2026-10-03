"""
orchestrator.py — Pipeline coordinator for the evaluation workflow.

Current pipeline (Brick 7):
    1. general_analysis  — extracts title, summary, problem, solution
    2. coordinator       — synthesises agent results into overall recommendation

The coordinator receives only the structured agent outputs, never the raw
proposal text.  If the coordinator call fails for any reason, the four
agent results are still returned with a "coordinator_error" field so
persistence and display are not blocked.

Public API:
    run_full_evaluation(proposal_text, filename, model, timeout)
        → dict  (ready to be passed directly to save_evaluation and
                 returned from /api/analyze)
"""
import logging
from typing import Any, Dict, Optional

from app.services.general_analysis import analyze_proposal
from app.agents.coordinator_agent import run_coordinator
from app.services.llm_client import LLMClientError

logger = logging.getLogger(__name__)

# ── Internal agent-name constant (general_analysis.py may not export one) ─────
# We define it here so the coordinator prompt always has a consistent label.
_GA_AGENT_NAME = "general_analysis"


def run_full_evaluation(
    proposal_text: str,
    filename:      str,
    model:         Optional[str] = None,
    timeout:       Optional[float] = None,
) -> Dict[str, Any]:
    """
    Run the complete evaluation pipeline for one proposal.

    Returns a dict with:
        analysis          — general_analysis result (always present)
        coordinator       — coordinator synthesis dict, or None + coordinator_error
        coordinator_error — str error message if coordinator failed, else absent
        _agent_statuses   — dict of { agent_name: "completed"|"failed" }

    This dict is intended to be:
      - Returned directly from POST /api/analyze (merged with document metadata)
      - Passed to save_evaluation() for persistence
    """
    agent_statuses: Dict[str, str] = {}

    # ── Stage 1: General analysis ──────────────────────────────────────────────
    try:
        analysis = analyze_proposal(proposal_text)
        # Tag with completion status for the coordinator
        analysis_for_coord = dict(analysis)
        analysis_for_coord["_status"] = "completed"
        agent_statuses[_GA_AGENT_NAME] = "completed"
    except LLMClientError:
        # Re-raise — if the core analysis fails there is nothing to synthesise
        raise
    except Exception as exc:
        # Unexpected internal error — surface it rather than silently swallowing
        raise RuntimeError(f"general_analysis stage failed: {exc}") from exc

    # ── Stage 2: Coordinator synthesis ────────────────────────────────────────
    # Input: only the structured results from Stage 1 (and future agents).
    # The coordinator must not receive proposal_text.
    title = analysis.get("title_or_topic") or filename

    agent_results_for_coord: Dict[str, Dict[str, Any]] = {
        _GA_AGENT_NAME: analysis_for_coord,
    }

    coordinator_result: Optional[Dict[str, Any]] = None
    coordinator_error:  Optional[str] = None

    try:
        coordinator_result = run_coordinator(
            title=title,
            agent_results=agent_results_for_coord,
            model=model,
            timeout=timeout,
        )

        # If run_coordinator returned an error dict (JSON parse failure)
        if "coordinator_error" in coordinator_result:
            coordinator_error  = coordinator_result.get("coordinator_error",
                                                         "JSON parsing failed")
            coordinator_result = None
            agent_statuses["coordinator"] = "failed"
        else:
            agent_statuses["coordinator"] = "completed"

    except LLMClientError as llm_err:
        # Ollama offline / model missing — non-fatal for the evaluation itself
        coordinator_error = str(llm_err)
        agent_statuses["coordinator"] = "failed"
        logger.warning("Coordinator LLMClientError: %s", coordinator_error)

    except Exception as exc:
        coordinator_error = f"Unexpected coordinator error: {exc}"
        agent_statuses["coordinator"] = "failed"
        logger.exception("Coordinator unexpected failure")

    # ── Assemble result dict ───────────────────────────────────────────────────
    result: Dict[str, Any] = {
        "analysis":       analysis,
        "coordinator":    coordinator_result,   # None if failed
        "_agent_statuses": agent_statuses,
    }

    if coordinator_error:
        result["coordinator_error"] = coordinator_error

    return result
