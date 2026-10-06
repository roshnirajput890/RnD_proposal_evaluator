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
  • Return ONLY one raw JSON object with no markdown or extra text.

Coordinator-specific Ollama options:
  • Uses larger num_ctx (8192) to fit combined agent outputs.
  • Uses larger num_predict (1200) for longer JSON response.
  • Uses lower temperature (0.1) for deterministic output.
"""
import json
import logging
import time
from typing import Any, Dict, Optional

from app.services.llm_client import call_llm_json
from app.config import COORDINATOR_NUM_CTX, COORDINATOR_NUM_PREDICT, COORDINATOR_TEMPERATURE

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
  (a) the structured outputs of specialist agents (summary, top 3 findings each), and
  (b) the PYTHON-COMPUTED overall score and score_band — these are calculated
      by deterministic weighted-average logic, NOT by you.

STRICT RULES:
1. You have NOT seen the original proposal text. Work only from what you receive.
2. Every key strength MUST name the agent that produced it.
3. Every key risk MUST name the agent that flagged it and include severity (High|Medium|Low).
4. Do NOT invent facts. If something is not in the agent results, say so.
5. If any agent has status "failed" or "error", set coordinator_confidence to "Low".
6. preliminary_recommendation MUST be exactly the score_band provided.
7. Novelty in this version has NO external literature verification. State this limitation.
8. Keep all text fields SHORT (1-2 sentences for summaries, 1 sentence for points).
9. The recommendation is ADVISORY only. A human reviewer decides.

RESPONSE FORMAT — Return ONLY a valid JSON object with these fields and no markdown:

{
  "overall_summary": "1-2 sentence synthesis",
  "key_strengths": [{"point": "1 sentence", "agent": "agent_name", "severity": "N/A"}],
  "key_risks": [{"point": "1 sentence", "agent": "agent_name", "severity": "High|Medium|Low"}],
  "critical_missing": ["item"],
  "questions": ["question"],
  "preliminary_recommendation": "same as score_band",
  "reasoning": "1-2 sentences explaining score_band",
  "confidence": "High|Medium|Low"
}
"""


def _extract_essential_fields(agent_name: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract only essential fields from agent results to reduce coordinator prompt size.
    Keeps: score, summary, and top 3 findings (point + severity).
    Drops: detailed analysis, full evidence, internal fields.
    """
    essential = {"_status": result.get("_status", "completed"), "agent": agent_name}
    
    # All agents: score and summary
    if "score" in result:
        essential["score"] = result["score"]
    if "score_justification" in result:
        essential["summary"] = result["score_justification"]
    elif "summary" in result:
        essential["summary"] = result["summary"]
    
    # Top 3 findings: point + severity (if available)
    findings = []
    if "findings" in result and isinstance(result["findings"], list):
        for finding in result["findings"][:3]:
            if isinstance(finding, dict):
                point_item = {
                    "point": finding.get("point", ""),
                }
                if "severity" in finding:
                    point_item["severity"] = finding["severity"]
                findings.append(point_item)
    
    if findings:
        essential["top_findings"] = findings
    
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
            max_tokens=COORDINATOR_NUM_PREDICT,
            num_ctx=COORDINATOR_NUM_CTX,
            temperature=COORDINATOR_TEMPERATURE,
        )
        elapsed = time.perf_counter() - _t0
        logger.info("TIMING [coordinator] done: %.1fs", elapsed)
        
        # Log done_reason and raw response if available
        if "done_reason" in result:
            logger.info("Ollama done_reason: %s", result["done_reason"])
        if result.get("error"):
            logger.error("Coordinator JSON parse failed. Raw response (first 500 chars): %s",
                        result.get("raw_response", "N/A")[:500])
    except Exception as exc:
        logger.error("Coordinator LLM call failed: %s", exc)
        # Return fallback instead of raising
        return _build_fallback_coordinator(scores, any_failed)

    # If JSON parsing failed, build fallback from scores
    if "error" in result and "overall_summary" not in result:
        logger.warning("Coordinator synthesis failed; building fallback from scores")
        return _build_fallback_coordinator(scores, any_failed)

    return _normalise(result, any_failed, scores)




def _build_fallback_coordinator(scores: Dict[str, Any], any_failed: bool) -> Dict[str, Any]:
    """
    Build a deterministic fallback coordinator response when AI synthesis fails.
    Uses the computed weighted score and recommendation label, plus a marker.
    """
    computed_band = scores.get("score_band", "Insufficient Information")
    
    return {
        "overall_summary": f"Automated evaluation summary: {computed_band} (AI synthesis unavailable).",
        "key_strengths": [],
        "key_risks": [],
        "conflicts_or_tensions": [],
        "critical_missing_information": ["Full coordinator analysis could not be generated."],
        "questions_for_human_reviewer": ["Review the agent results and scores above."],
        "preliminary_recommendation": computed_band,
        "recommendation_reasoning": f"Based on computed score band: {computed_band}. AI synthesis of findings was unavailable.",
        "coordinator_confidence": "Low" if any_failed else "Medium",
        "_auto_generated": True,
    }


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
