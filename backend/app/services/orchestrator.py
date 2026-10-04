"""
orchestrator.py — Evaluation pipeline (Brick 10).

Pipeline:
  1. general_analysis   → structural extraction (title, summary, problem, solution)
  2. novelty_agent      → 3-step: query extraction → OpenAlex search → scored comparison
  3. technical_agent    → single-step technical feasibility assessment
  4. financial_agent    → 3-step: budget extraction → validation → assessment
  5. impact_agent       → single-step societal/strategic impact assessment
  6. scoring.py         → weighted overall_score + score_band (pure Python)
  7. coordinator_agent  → synthesis referencing computed scores + novelty evidence flag
"""
import logging
from typing import Any, Dict, Optional

from app.services.general_analysis import analyze_proposal, AGENT_NAME as GA_NAME
from app.agents.novelty_agent import run_novelty_agent, AGENT_NAME as NOV_NAME
from app.agents.technical_agent import run_technical_agent, AGENT_NAME as TECH_NAME
from app.agents.financial_agent import run_financial_agent, AGENT_NAME as FIN_NAME
from app.agents.impact_agent import run_impact_agent, AGENT_NAME as IMP_NAME
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
        analysis          — structural extraction result (title, summary, problem, solution)
        novelty           — novelty_agent result (score, papers, evidence flag, …)
        technical         — technical_agent result (score, findings, …)
        financial         — financial_agent result (score, budget_validation, …)
        impact            — impact_agent result (score, findings, …)
        scoring           — ScoringResult as dict (overall_score, score_band, …)
        coordinator       — coordinator synthesis, or None on failure
        coordinator_error — str if coordinator failed, else absent
        _agent_statuses   — {agent_name: "completed"|"failed"}
    """
    agent_statuses: Dict[str, str] = {}

    # ── Stage 1: Structural extraction (general_analysis) ─────────────────────
    try:
        analysis = analyze_proposal(proposal_text)
        analysis_for_coord = {**analysis, "_status": "completed"}
        agent_statuses[GA_NAME] = "completed"
    except LLMClientError:
        raise   # propagate — Ollama offline is fatal for the whole pipeline
    except Exception as exc:
        raise RuntimeError(f"general_analysis stage failed: {exc}") from exc

    # ── Stage 2: Novelty evaluation (with external paper search) ─────────────
    novelty = _run_agent_safe(
        run_novelty_agent, "novelty", proposal_text, model, timeout, agent_statuses
    )
    novelty_for_coord = {**novelty, "_status": agent_statuses.get(NOV_NAME, "failed")}

    # ── Stage 3: Technical feasibility evaluation ────────────────────────────
    technical = _run_agent_safe(
        run_technical_agent, "technical", proposal_text, model, timeout, agent_statuses
    )
    technical_for_coord = {**technical, "_status": agent_statuses.get(TECH_NAME, "failed")}

    # ── Stage 4: Financial viability evaluation ──────────────────────────────
    financial = _run_agent_safe(
        run_financial_agent, "financial", proposal_text, model, timeout, agent_statuses
    )
    financial_for_coord = {**financial, "_status": agent_statuses.get(FIN_NAME, "failed")}

    # ── Stage 5: Impact evaluation ───────────────────────────────────────────
    impact = _run_agent_safe(
        run_impact_agent, "impact", proposal_text, model, timeout, agent_statuses
    )
    impact_for_coord = {**impact, "_status": agent_statuses.get(IMP_NAME, "failed")}

    # ── Stage 6: Scoring (pure Python — no LLM) ──────────────────────────────
    logger.info(
        "SCORING: novelty=%s, technical=%s, financial=%s, impact=%s",
        novelty.get("score"), technical.get("score"),
        financial.get("score"), impact.get("score")
    )

    scoring_result = compute_scores(
        novelty   = novelty.get("score"),
        technical = technical.get("score"),
        financial = financial.get("score"),
        impact    = impact.get("score"),
    )
    scoring_dict = scoring_result_to_dict(scoring_result)

    # ── Stage 7: Coordinator synthesis ───────────────────────────────────────
    title = analysis.get("title_or_topic") or filename

    coordinator_result: Optional[Dict[str, Any]] = None
    coordinator_error:  Optional[str]  = None

    try:
        coordinator_result = run_coordinator(
            title         = title,
            agent_results = {
                GA_NAME:   analysis_for_coord,
                NOV_NAME:  novelty_for_coord,
                TECH_NAME: technical_for_coord,
                FIN_NAME:  financial_for_coord,
                IMP_NAME:  impact_for_coord,
            },
            scores                = scoring_dict,
            external_evidence_used = novelty.get("external_evidence_used", False),
            model   = model,
            timeout = timeout,
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
        "novelty":         novelty,
        "technical":       technical,
        "financial":       financial,
        "impact":          impact,
        "scoring":         scoring_dict,
        "coordinator":     coordinator_result,
        "_agent_statuses": agent_statuses,
    }
    if coordinator_error:
        result["coordinator_error"] = coordinator_error

    return result


def _run_agent_safe(
    agent_func,
    agent_display_name: str,
    proposal_text: str,
    model: Optional[str],
    timeout: Optional[float],
    agent_statuses: Dict[str, str],
) -> Dict[str, Any]:
    """
    Run an agent function with error handling.
    Returns agent result dict with status field.
    Updates agent_statuses dict in place.
    """
    agent_name = agent_func.__module__.split(".")[-1]  # e.g., "novelty_agent"
    
    try:
        result = agent_func(
            proposal_text=proposal_text,
            model=model,
            timeout=timeout,
        )
        
        # Check if agent returned failure status
        if result.get("status") == "failed":
            agent_statuses[agent_name] = "failed"
            logger.warning("%s returned status='failed'", agent_display_name)
        else:
            agent_statuses[agent_name] = "completed"
        
        return result
        
    except LLMClientError as llm_err:
        # Ollama offline during this agent — mark failed but continue
        logger.warning("%s LLMClientError: %s", agent_display_name, llm_err)
        agent_statuses[agent_name] = "failed"
        return {
            "score": None,
            "score_justification": f"[score unavailable] Ollama unreachable during {agent_display_name} evaluation.",
            "summary": f"{agent_display_name.capitalize()} evaluation failed — Ollama was unreachable.",
            "status": "failed",
        }
    except Exception as exc:
        logger.exception("%s unexpected failure", agent_display_name)
        agent_statuses[agent_name] = "failed"
        return {
            "score": None,
            "score_justification": f"[score unavailable] {exc}",
            "summary": f"{agent_display_name.capitalize()} evaluation failed: {exc}",
            "status": "failed",
        }
