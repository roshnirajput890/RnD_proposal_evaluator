"""
coordinator_agent.py — Coordinator / synthesis agent.

Brick 8 update:
  run_coordinator() now accepts a `scores` dict (the output of scoring.py).
  The scores and Python-computed score_band are injected into the prompt so
  the coordinator explains / justifies them rather than computing its own.
  The preliminary_recommendation field is set to the Python-derived score_band —
  the coordinator must not override it with a different value.

Rules encoded in the system prompt:
  • Every strength/risk must cite the specific agent.
  • The coordinator does not compute scores — it receives them.
  • preliminary_recommendation MUST equal the score_band provided.
  • Novelty has no external literature evidence in this version.
  • If any agent failed, confidence is ≤ Medium.
  • The recommendation is advisory; human reviewer decides.
"""
import json
import logging
import time
from typing import Any, Dict, Optional

from app.services.llm_client import call_llm_json

logger = logging.getLogger(__name__)

VALID_RECOMMENDATIONS = {
    "Recommend", "Revise and Resubmit",
    "Not Recommended", "Insufficient Information",
}
VALID_CONFIDENCE = {"High", "Medium", "Low"}

_COORDINATOR_SYSTEM = """\
You are the Coordinator Agent in an R&D proposal evaluation pipeline.

Your role is SYNTHESIS, not new analysis and not numeric scoring.
You receive:
  (a) the structured JSON outputs of specialist agents, and
  (b) the PYTHON-COMPUTED overall score and score_band — these are calculated
      by deterministic weighted-average logic, NOT by you.

STRICT RULES:
1. You have NOT seen the original proposal text. Work only from what you receive.
2. Every key_strength MUST name the agent that produced it (supported_by_agent).
3. Every key_risk MUST name the agent that flagged it (supported_by_agent).
4. Do NOT invent facts.  If something is not in the agent results, say so.
5. If any agent has status "failed" or "error", state the evaluation is INCOMPLETE
   and set coordinator_confidence to "Low".
6. preliminary_recommendation MUST be exactly equal to the score_band you are given.
   Do not change it. Your job is to EXPLAIN it, not override it.
7. Novelty in this version has NO external literature verification.
   State this limitation when discussing novelty.
8. If agents contradict each other, list the tension in conflicts_or_tensions.
9. List concrete, answerable questions in questions_for_human_reviewer.
10. The recommendation is ADVISORY only.  A human reviewer decides.

RESPONSE FORMAT — ONLY a valid JSON object, no markdown, no extra text:

{
  "overall_summary": "2-4 sentence synthesis.",
  "key_strengths": [{"point": "...", "supported_by_agent": "agent_name"}],
  "key_risks": [{"point": "...", "severity": "High|Medium|Low", "supported_by_agent": "agent_name"}],
  "conflicts_or_tensions": [{"description": "...", "between_agents": ["a", "b"]}],
  "critical_missing_information": ["..."],
  "questions_for_human_reviewer": ["..."],
  "preliminary_recommendation": "<must equal the score_band you received>",
  "recommendation_reasoning": "One paragraph explaining why this band was reached.",
  "coordinator_confidence": "High|Medium|Low"
}
"""


def _extract_essential_fields(agent_name: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract only essential fields from agent results to reduce coordinator prompt size.
    Keeps: summary/justification fields, scores, key findings. Drops full details.
    """
    essential = {"_status": result.get("_status", "completed")}
    
    if agent_name == "novelty_agent":
        # Keep score, justification, key findings
        essential.update({
            "score": result.get("score"),
            "score_justification": result.get("score_justification"),
            "claimed_innovation": result.get("claimed_innovation"),
            "external_evidence_used": result.get("external_evidence_used"),
            "novelty_confidence_note": result.get("novelty_confidence_note"),
            "retrieved_paper_count": result.get("retrieved_paper_count"),
        })
        # Keep only top 2 closest papers, not all
        closest = result.get("closest_papers", [])
        if closest:
            essential["closest_papers"] = closest[:2]
    
    elif agent_name == "general_analysis":
        # Keep summary, title, category, key findings
        essential.update({
            "title_or_topic": result.get("title_or_topic"),
            "category": result.get("category"),
            "summary": result.get("summary"),
            "key_findings": result.get("key_findings"),
        })
    
    else:
        # For other agents, keep non-internal fields but drop large blobs
        essential.update({
            k: v for k, v in result.items()
            if not k.startswith("_") and not isinstance(v, (list, dict)) or k in ("key_findings", "summary")
        })
    
    return essential


def _build_user_prompt(
    title:                 str,
    agent_results:         Dict[str, Dict[str, Any]],
    scores:                Dict[str, Any],
    external_evidence_used: bool = False,
) -> str:
    evidence_note = (
        "Novelty was assessed WITH retrieved external papers (OpenAlex search)."
        if external_evidence_used
        else
        "Novelty was assessed WITHOUT external papers (search returned no results or was unavailable). "
        "Do NOT imply strong novelty confirmation — the assessment is text-only."
    )

    lines = [
        f'Proposal title: "{title}"',
        "",
        "=== PYTHON-COMPUTED SCORES (do not recalculate — explain these) ===",
        json.dumps(scores, indent=2, ensure_ascii=False),
        "",
        f"The preliminary_recommendation you output MUST be: "
        f"\"{scores.get('score_band', 'Insufficient Information')}\"",
        "",
        f"=== NOVELTY EVIDENCE NOTE ===",
        evidence_note,
        "",
        "=== AGENT RESULTS (essential fields only) ===",
    ]

    for agent_name, result in agent_results.items():
        lines.append(f"--- AGENT: {agent_name} ---")
        clean = _extract_essential_fields(agent_name, result)
        lines.append(json.dumps(clean, indent=2, ensure_ascii=False))
        lines.append("")

    lines += [
        "Synthesise the above. Do not invent facts.",
        "Your preliminary_recommendation MUST match the score_band shown above.",
    ]
    return "\n".join(lines)


def run_coordinator(
    title:                 str,
    agent_results:         Dict[str, Dict[str, Any]],
    scores:                Optional[Dict[str, Any]] = None,
    external_evidence_used: bool = False,
    model:                 Optional[str]  = None,
    timeout:               Optional[float] = None,
) -> Dict[str, Any]:
    any_failed = any(
        r.get("_status") in ("failed", "error")
        for r in agent_results.values()
    )

    scores = scores or {}
    user_prompt = _build_user_prompt(
        title, agent_results, scores, external_evidence_used
    )

    logger.info("TIMING [coordinator] start")
    _t0 = time.perf_counter()
    
    try:
        result = call_llm_json(
            system_prompt=_COORDINATOR_SYSTEM,
            user_prompt=user_prompt,
            model=model,
            timeout=timeout,
        )
        logger.info("TIMING [coordinator] done: %.1fs", time.perf_counter() - _t0)
    except Exception as exc:
        # Log the raw response text if available to debug JSON parse failures
        if hasattr(exc, 'raw_response'):
            logger.error(
                "Coordinator LLM call failed with exception. Raw response (first 1000 chars):\n%s",
                str(exc.raw_response)[:1000]
            )
        logger.error("Coordinator LLM call failed: %s", exc)
        raise

    if "error" in result and "overall_summary" not in result:
        return {
            "coordinator_error": result.get("error"),
            "raw_response":      result.get("raw_response"),
        }

    return _normalise(result, any_failed, scores)


def _normalise(
    raw:        Dict[str, Any],
    any_failed: bool,
    scores:     Dict[str, Any],
) -> Dict[str, Any]:
    computed_band = scores.get("score_band", "Insufficient Information")

    defaults: Dict[str, Any] = {
        "overall_summary":              "Not provided by coordinator.",
        "key_strengths":                [],
        "key_risks":                    [],
        "conflicts_or_tensions":        [],
        "critical_missing_information": [],
        "questions_for_human_reviewer": [],
        "preliminary_recommendation":   computed_band,
        "recommendation_reasoning":     "Coordinator did not provide reasoning.",
        "coordinator_confidence":       "Low",
    }

    out = {**defaults, **raw}

    for list_key in ("key_strengths", "key_risks", "conflicts_or_tensions",
                     "critical_missing_information", "questions_for_human_reviewer"):
        if not isinstance(out[list_key], list):
            out[list_key] = []

    # Force recommendation to match the Python-computed band
    out["preliminary_recommendation"] = computed_band

    if out["coordinator_confidence"] not in VALID_CONFIDENCE:
        out["coordinator_confidence"] = "Low"
    if any_failed and out["coordinator_confidence"] == "High":
        out["coordinator_confidence"] = "Medium"

    return out
