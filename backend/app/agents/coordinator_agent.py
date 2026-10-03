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
from typing import Any, Dict, Optional

from app.services.llm_client import call_llm_json

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


def _build_user_prompt(
    title:         str,
    agent_results: Dict[str, Dict[str, Any]],
    scores:        Dict[str, Any],
) -> str:
    lines = [
        f'Proposal title: "{title}"',
        "",
        "=== PYTHON-COMPUTED SCORES (do not recalculate — explain these) ===",
        json.dumps(scores, indent=2, ensure_ascii=False),
        "",
        f"The preliminary_recommendation you output MUST be: "
        f"\"{scores.get('score_band', 'Insufficient Information')}\"",
        "",
        "=== AGENT RESULTS ===",
    ]

    for agent_name, result in agent_results.items():
        status = result.get("_status", "completed")
        lines.append(f"--- AGENT: {agent_name}  (status: {status}) ---")
        clean = {k: v for k, v in result.items() if not k.startswith("_")}
        lines.append(json.dumps(clean, indent=2, ensure_ascii=False))
        lines.append("")

    lines += [
        "Synthesise the above. Do not invent facts.",
        "Your preliminary_recommendation MUST match the score_band shown above.",
    ]
    return "\n".join(lines)


def run_coordinator(
    title:         str,
    agent_results: Dict[str, Dict[str, Any]],
    scores:        Optional[Dict[str, Any]] = None,
    model:         Optional[str]  = None,
    timeout:       Optional[float] = None,
) -> Dict[str, Any]:
    any_failed = any(
        r.get("_status") in ("failed", "error")
        for r in agent_results.values()
    )

    scores = scores or {}
    user_prompt = _build_user_prompt(title, agent_results, scores)

    result = call_llm_json(
        system_prompt=_COORDINATOR_SYSTEM,
        user_prompt=user_prompt,
        model=model,
        timeout=timeout,
    )

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
