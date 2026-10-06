"""
orchestrator.py — Evaluation pipeline (Brick 10 + parallelization + performance optimizations).

Pipeline:
  1. general_analysis   → structural extraction (title, summary, problem, solution)
  2-5. Parallel agents  → Novelty, Technical, Financial, Impact (sequential or parallel)
  6. scoring.py         → weighted overall_score + score_band (pure Python)
  7. coordinator_agent  → synthesis referencing computed scores + novelty evidence flag

Parallelization controlled by PARALLEL_AGENTS and AGENT_CONCURRENCY env vars.
Set AGENT_CONCURRENCY=1 for sequential execution (better for CPU-only systems).
"""
import asyncio
import logging
import time
from typing import Any, Dict, Optional

from app.services.general_analysis import analyze_proposal, AGENT_NAME as GA_NAME
from app.agents.novelty_agent import run_novelty_agent, AGENT_NAME as NOV_NAME
from app.agents.technical_agent import run_technical_agent, AGENT_NAME as TECH_NAME
from app.agents.financial_agent import run_financial_agent, AGENT_NAME as FIN_NAME
from app.agents.impact_agent import run_impact_agent, AGENT_NAME as IMP_NAME
from app.services.scoring import compute_scores, scoring_result_to_dict
from app.agents.coordinator_agent import run_coordinator
from app.services.llm_client import LLMClientError
from app.services.text_chunker import extract_relevant_text
from app.config import (
    PARALLEL_AGENTS, AGENT_CONCURRENCY, AGENT_TIMEOUT_SECONDS, NOVELTY_TIMEOUT_SECONDS, MAX_CHARS_PER_AGENT
)

logger = logging.getLogger(__name__)

# Progress tracking state (in-memory)
_progress_state: Dict[str, Dict[str, Any]] = {}


def set_progress(eval_id: str, current_agent: str, completed: int, total: int):
    """Update progress state for an evaluation."""
    _progress_state[eval_id] = {
        "current_agent": current_agent,
        "completed": completed,
        "total": total,
        "timestamp": time.time()
    }


def get_progress(eval_id: str) -> Optional[Dict[str, Any]]:
    """Get progress state for an evaluation."""
    return _progress_state.get(eval_id)


def clear_progress(eval_id: str):
    """Clear progress state for an evaluation."""
    _progress_state.pop(eval_id, None)


async def _run_agents_parallel(
    proposal_text: str,
    model: Optional[str],
    timeout: Optional[float],
    agent_statuses: Dict[str, str],
    evaluation_id: Optional[str] = None,
):
    """
    Run four independent agents with concurrency control (asyncio.Semaphore).
    
    Returns: (novelty, technical, financial, impact) results
    """
    semaphore = asyncio.Semaphore(AGENT_CONCURRENCY)
    
    agent_order = [
        (run_novelty_agent, NOV_NAME, "novelty", 2),
        (run_technical_agent, TECH_NAME, "technical", 3),
        (run_financial_agent, FIN_NAME, "financial", 4),
        (run_impact_agent, IMP_NAME, "impact", 5),
    ]
    
    async def run_with_semaphore(agent_func, agent_name, display_name, step_num):
        async with semaphore:
            if evaluation_id:
                set_progress(evaluation_id, display_name, step_num - 1, 6)
            
            # Run in executor since agent functions are sync
            loop = asyncio.get_event_loop()
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        _run_agent_safe,
                        agent_func,
                        display_name,
                        proposal_text,
                        model,
                        agent_statuses,
                    ),
                    timeout=AGENT_TIMEOUT_SECONDS
                )
                return result
            except asyncio.TimeoutError:
                logger.warning("%s agent timed out after %.1fs", display_name, AGENT_TIMEOUT_SECONDS)
                agent_statuses[agent_name] = "failed"
                return {
                    "score": None,
                    "score_justification": f"[score unavailable] {display_name.capitalize()} agent timed out after {int(AGENT_TIMEOUT_SECONDS)} seconds.",
                    "summary": f"{display_name.capitalize()} evaluation timed out — try a shorter document.",
                    "status": "failed",
                    "error_code": "agent_timeout",
                }
    
    # Kick off all four agents with concurrency limit
    results = await asyncio.gather(
        *[run_with_semaphore(*agent_info) for agent_info in agent_order]
    )
    
    return results  # (novelty, technical, financial, impact)


def run_full_evaluation(
    proposal_text: str,
    filename:      str,
    model:         Optional[str]  = None,
    timeout:       Optional[float] = None,
    evaluation_id: Optional[str]  = None,
) -> Dict[str, Any]:
    """
    Run the complete evaluation pipeline.

    Args:
        proposal_text: Full proposal text
        filename: Original filename
        model: Optional LLM model override
        timeout: Optional timeout override
        evaluation_id: Optional ID for progress tracking

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
        truncation_applied — bool indicating if any agent had truncated input
    """
    pipeline_start_time = time.time()
    agent_statuses: Dict[str, str] = {}
    truncation_flags: Dict[str, bool] = {}

    # ── Stage 1: Structural extraction (general_analysis) ─────────────────────
    try:
        if evaluation_id:
            set_progress(evaluation_id, "general_analysis", 0, 6)
        
        logger.info("[PIPELINE] Starting general_analysis")
        stage_start = time.time()
        
        analysis = analyze_proposal(proposal_text)
        analysis_for_coord = {**analysis, "_status": "completed"}
        agent_statuses[GA_NAME] = "completed"
        
        elapsed = time.time() - stage_start
        logger.info("[TIMING] general_analysis: completed in %.1fs", elapsed)
    except LLMClientError:
        clear_progress(evaluation_id) if evaluation_id else None
        raise   # propagate — Ollama offline is fatal for the whole pipeline
    except Exception as exc:
        clear_progress(evaluation_id) if evaluation_id else None
        raise RuntimeError(f"general_analysis stage failed: {exc}") from exc

    # ── Stage 2-5: Run four independent agents ────────────────────────────────
    if PARALLEL_AGENTS and AGENT_CONCURRENCY > 1:
        logger.info("Running agents in parallel (max %d concurrent)", AGENT_CONCURRENCY)
        novelty, technical, financial, impact = asyncio.run(
            _run_agents_parallel(proposal_text, model, timeout, agent_statuses, evaluation_id)
        )
    else:
        logger.info("Running agents sequentially (AGENT_CONCURRENCY=%d)", AGENT_CONCURRENCY)
        
        if evaluation_id:
            set_progress(evaluation_id, "novelty", 1, 6)
        novelty = _run_agent_safe_with_timeout(
            run_novelty_agent, "novelty", proposal_text, model, timeout, agent_statuses, truncation_flags,
            agent_timeout=NOVELTY_TIMEOUT_SECONDS
        )
        
        if evaluation_id:
            set_progress(evaluation_id, "technical", 2, 6)
        technical = _run_agent_safe_with_timeout(
            run_technical_agent, "technical", proposal_text, model, timeout, agent_statuses, truncation_flags
        )
        
        if evaluation_id:
            set_progress(evaluation_id, "financial", 3, 6)
        financial = _run_agent_safe_with_timeout(
            run_financial_agent, "financial", proposal_text, model, timeout, agent_statuses, truncation_flags
        )
        
        if evaluation_id:
            set_progress(evaluation_id, "impact", 4, 6)
        impact = _run_agent_safe_with_timeout(
            run_impact_agent, "impact", proposal_text, model, timeout, agent_statuses, truncation_flags
        )

    novelty_for_coord = {**novelty, "_status": agent_statuses.get(NOV_NAME, "failed")}
    technical_for_coord = {**technical, "_status": agent_statuses.get(TECH_NAME, "failed")}
    financial_for_coord = {**financial, "_status": agent_statuses.get(FIN_NAME, "failed")}
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
    if evaluation_id:
        set_progress(evaluation_id, "coordinator", 5, 6)
    
    title = analysis.get("title_or_topic") or filename
    coordinator_result: Optional[Dict[str, Any]] = None
    coordinator_error:  Optional[str]  = None

    try:
        logger.info("[PIPELINE] Starting coordinator synthesis")
        coord_start = time.time()
        
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
            agent_statuses = agent_statuses,
        )

        elapsed = time.time() - coord_start
        logger.info("[TIMING] coordinator: completed in %.1fs", elapsed)

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

    # ── Pipeline completion ───────────────────────────────────────────────────
    total_time = time.time() - pipeline_start_time
    success_count = sum(1 for status in agent_statuses.values() if status == "completed")
    fail_count = len(agent_statuses) - success_count
    
    logger.info(
        "[PIPELINE] Total time: %.1fs | Success: %d/%d | Failed: %d/%d",
        total_time, success_count, len(agent_statuses), fail_count, len(agent_statuses)
    )
    
    if evaluation_id:
        clear_progress(evaluation_id)

    result: Dict[str, Any] = {
        "analysis":        analysis,
        "novelty":         novelty,
        "technical":       technical,
        "financial":       financial,
        "impact":          impact,
        "scoring":         scoring_dict,
        "coordinator":     coordinator_result,
        "_agent_statuses": agent_statuses,
        "truncation_applied": any(truncation_flags.values()),
    }
    if coordinator_error:
        result["coordinator_error"] = coordinator_error

    return result


def _run_agent_safe(
    agent_func,
    agent_display_name: str,
    proposal_text: str,
    model: Optional[str],
    agent_statuses: Dict[str, str],
) -> Dict[str, Any]:
    """
    Run an agent function with error handling (for parallel mode).
    
    Agent-level timeout is enforced by asyncio.wait_for in the caller.
    LLM request timeout is controlled by REQUEST_TIMEOUT_SECONDS in config.
    
    Returns agent result dict with status field.
    Updates agent_statuses dict in place.
    """
    agent_name = agent_func.__module__.split(".")[-1]  # e.g., "novelty_agent"
    
    # Extract relevant text for this agent
    chunk = extract_relevant_text(proposal_text, agent_display_name, MAX_CHARS_PER_AGENT)
    
    try:
        agent_start = time.time()
        result = agent_func(
            proposal_text=chunk["text"],
            model=model,
        )
        elapsed = time.time() - agent_start
        
        logger.info(
            "[TIMING] %s agent: %d chars sent, completed in %.1fs",
            agent_display_name, chunk["chars_selected"], elapsed
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


def _run_agent_safe_with_timeout(
    agent_func,
    agent_display_name: str,
    proposal_text: str,
    model: Optional[str],
    timeout: Optional[float],
    agent_statuses: Dict[str, str],
    truncation_flags: Dict[str, bool],
    agent_timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Run an agent function with timeout and error handling (for sequential mode).
    
    Agent-level timeout is enforced by ThreadPoolExecutor.result(timeout=agent_timeout).
    If agent_timeout is None, uses AGENT_TIMEOUT_SECONDS.
    LLM request timeout is controlled by REQUEST_TIMEOUT_SECONDS in config.
    The timeout parameter is kept for backward compatibility but not used for agent execution.
    
    Returns agent result dict with status field.
    Updates agent_statuses and truncation_flags dicts in place.
    """
    agent_name = agent_func.__module__.split(".")[-1]  # e.g., "novelty_agent"
    
    # Extract relevant text for this agent
    chunk = extract_relevant_text(proposal_text, agent_display_name, MAX_CHARS_PER_AGENT)
    truncation_flags[agent_display_name] = chunk["truncated"]
    
    agent_start = time.time()
    
    # Use agent-specific timeout if provided, otherwise use AGENT_TIMEOUT_SECONDS
    timeout_to_use = agent_timeout if agent_timeout is not None else AGENT_TIMEOUT_SECONDS
    
    # Use threading for timeout since these are sync functions
    import concurrent.futures
    
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                agent_func,
                proposal_text=chunk["text"],
                model=model,
            )
            
            try:
                result = future.result(timeout=timeout_to_use)
                elapsed = time.time() - agent_start
                
                logger.info(
                    "[TIMING] %s agent: %d chars sent, completed in %.1fs",
                    agent_display_name, chunk["chars_selected"], elapsed
                )
                
                # Check if agent returned failure status
                if result.get("status") == "failed":
                    agent_statuses[agent_name] = "failed"
                    logger.warning("%s returned status='failed'", agent_display_name)
                else:
                    agent_statuses[agent_name] = "completed"
                
                return result
                
            except concurrent.futures.TimeoutError:
                elapsed = time.time() - agent_start
                logger.warning(
                    "[TIMING] %s agent: %d chars sent, TIMED OUT after %.1fs",
                    agent_display_name, chunk["chars_selected"], elapsed
                )
                agent_statuses[agent_name] = "failed"
                return {
                    "score": None,
                    "score_justification": f"[score unavailable] {agent_display_name.capitalize()} agent timed out after {int(timeout_to_use)} seconds.",
                    "summary": f"{agent_display_name.capitalize()} evaluation timed out — try a shorter document.",
                    "status": "failed",
                    "error_code": "agent_timeout",
                }
        
    except LLMClientError as llm_err:
        # Ollama offline during this agent — mark failed but continue
        elapsed = time.time() - agent_start
        logger.warning(
            "[TIMING] %s agent: %d chars sent, LLMClientError after %.1fs: %s",
            agent_display_name, chunk["chars_selected"], elapsed, llm_err
        )
        agent_statuses[agent_name] = "failed"
        return {
            "score": None,
            "score_justification": f"[score unavailable] Ollama unreachable during {agent_display_name} evaluation.",
            "summary": f"{agent_display_name.capitalize()} evaluation failed — Ollama was unreachable.",
            "status": "failed",
            "error_code": getattr(llm_err, "error_code", "llm_error"),
        }
    except Exception as exc:
        elapsed = time.time() - agent_start
        logger.exception(
            "[TIMING] %s agent: %d chars sent, unexpected failure after %.1fs",
            agent_display_name, chunk["chars_selected"], elapsed
        )
        agent_statuses[agent_name] = "failed"
        return {
            "score": None,
            "score_justification": f"[score unavailable] {exc}",
            "summary": f"{agent_display_name.capitalize()} evaluation failed: {exc}",
            "status": "failed",
        }
