"""
coordinator_agent.py — Coordinator / synthesis agent.

Receives ONLY the structured results from the general analysis agent
(and optionally other specialist agents in future bricks) plus the
proposal title.  It never sees the raw proposal text.

Returns a structured JSON synthesis with:
  overall_summary                   str
  key_strengths                     [{point, supported_by_agent}]
  key_risks                         [{point, severity, supported_by_agent}]
  conflicts_or_tensions             [{description, between_agents}]
  critical_missing_information      [str]
  questions_for_human_reviewer      [str]
  preliminary_recommendation        "Recommend" | "Revise and Resubmit"
                                  | "Not Recommended" | "Insufficient Information"
  recommendation_reasoning          str
  coordinator_confidence            "High" | "Medium" | "Low"

Design rules encoded in the system prompt:
  • Every strength and risk MUST cite the specific agent that produced it.
  • The coordinator must not invent new facts — only synthesise what agents found.
  • If any agent has status "failed", the evaluation is incomplete; confidence
    must be "Low" or "Medium" at most.
  • The recommendation is explicitly advisory; a human reviewer decides.
  • Novelty findings have no external evidence in this version — state that.
"""
import json
from typing import Any, Dict, List, Optional

from app.services.llm_client import call_llm_json, LLMClientError

# ── Valid recommendation values ───────────────────────────────────────────────

VALID_RECOMMENDATIONS = {
    "Recommend",
    "Revise and Resubmit",
    "Not Recommended",
    "Insufficient Information",
}

VALID_CONFIDENCE = {"High", "Medium", "Low"}


# ── System prompt ─────────────────────────────────────────────────────────────

_COORDINATOR_SYSTEM = """\
You are the Coordinator Agent in an R&D proposal evaluation pipeline.

Your role is SYNTHESIS, not new analysis. You receive the structured JSON
outputs produced by specialist evaluation agents and you produce a coherent
overall summary and preliminary recommendation.

STRICT RULES — follow all of them without exception:
1. You have NOT seen the original proposal text. You work ONLY from the
   agent results provided to you.
2. Every key strength you list MUST reference the specific agent name that
   produced the finding (e.g. "supported_by_agent": "general_analysis").
3. Every risk you list MUST reference the specific agent name that flagged it.
4. Do NOT invent, assume, or extrapolate facts beyond what the agents reported.
5. If any agent has status "failed" or "error", you MUST state in your summary
   that the evaluation is INCOMPLETE and set coordinator_confidence to "Low".
6. The preliminary_recommendation field is ADVISORY ONLY. A human reviewer
   makes the final decision. Do not present it as a final verdict.
7. The Novelty evaluation in this version does NOT consult external literature
   or citation databases. State this limitation explicitly in your summary if
   novelty is discussed.
8. If the agents' findings directly contradict each other, list the tension in
   conflicts_or_tensions — do not silently choose one side.
9. If critical information is missing (e.g. budget, timeline, methodology
   details were flagged as absent), list it in critical_missing_information.
10. questions_for_human_reviewer must be concrete, answerable questions a
    human reviewer could pursue — not vague statements.

RESPONSE FORMAT:
Respond with ONLY a valid JSON object. No explanation, no markdown code fences,
no extra text before or after. Match this schema exactly:

{
  "overall_summary": "A 2-4 sentence synthesis of what the agents found.",
  "key_strengths": [
    {"point": "...", "supported_by_agent": "agent_name"}
  ],
  "key_risks": [
    {"point": "...", "severity": "High|Medium|Low", "supported_by_agent": "agent_name"}
  ],
  "conflicts_or_tensions": [
    {"description": "...", "between_agents": ["agent_a", "agent_b"]}
  ],
  "critical_missing_information": ["..."],
  "questions_for_human_reviewer": ["..."],
  "preliminary_recommendation": "Recommend|Revise and Resubmit|Not Recommended|Insufficient Information",
  "recommendation_reasoning": "One paragraph explaining the recommendation.",
  "coordinator_confidence": "High|Medium|Low"
}
"""


def _build_user_prompt(
    title: str,
    agent_results: Dict[str, Dict[str, Any]],
) -> str:
    """
    Serialise the agent results into a structured prompt the coordinator reads.
    Each agent result is labelled with its name and status.
    """
    lines = [
        f'Proposal title: "{title}"',
        "",
        "The following agent results are available for synthesis.",
        "Each result is labelled with the agent name and its completion status.",
        "",
    ]

    for agent_name, result in agent_results.items():
        status = result.get("_status", "completed")
        lines.append(f"=== AGENT: {agent_name}  (status: {status}) ===")
        # Pretty-print the result, omitting internal _status key
        clean = {k: v for k, v in result.items() if not k.startswith("_")}
        lines.append(json.dumps(clean, indent=2, ensure_ascii=False))
        lines.append("")

    lines += [
        "Using ONLY the information above, produce your coordinator synthesis.",
        "Remember: do not invent facts; cite specific agents for every finding.",
    ]
    return "\n".join(lines)


def run_coordinator(
    title: str,
    agent_results: Dict[str, Dict[str, Any]],
    model: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Run the coordinator agent and return its structured JSON output.

    Args:
        title:         The proposal title or topic (from general_analysis output).
        agent_results: Dict of { agent_name: result_dict }.
                       Each result_dict may contain a "_status" key ("completed"
                       | "failed") that is stripped before the LLM call but used
                       to set context.
        model:         Optional model override.
        timeout:       Optional timeout override (seconds).

    Returns:
        Dict matching the coordinator schema.  On parse failure after retry,
        returns a structured error dict with "coordinator_error" key so the
        caller can still persist the agent results.

    Raises:
        LLMClientError: If Ollama is unreachable or the model is missing.
                        Callers should catch this and treat coordinator as
                        optional — the evaluation should still be saved.
    """
    any_failed = any(
        r.get("_status") in ("failed", "error")
        for r in agent_results.values()
    )

    user_prompt = _build_user_prompt(title, agent_results)

    # call_llm_json handles the validate-and-retry-once logic
    result = call_llm_json(
        system_prompt=_COORDINATOR_SYSTEM,
        user_prompt=user_prompt,
        model=model,
        timeout=timeout,
    )

    # If the underlying LLM returned a JSON-parse error dict
    if "error" in result and "overall_summary" not in result:
        return {
            "coordinator_error": result.get("error"),
            "raw_response":      result.get("raw_response"),
        }

    # Normalise and validate fields
    result = _normalise(result, any_failed)
    return result


def _normalise(raw: Dict[str, Any], any_failed: bool) -> Dict[str, Any]:
    """
    Ensure all required keys are present with sensible defaults.
    Clamp confidence to "Low" if any agent failed.
    """
    defaults: Dict[str, Any] = {
        "overall_summary":               "Not provided by coordinator.",
        "key_strengths":                 [],
        "key_risks":                     [],
        "conflicts_or_tensions":         [],
        "critical_missing_information":  [],
        "questions_for_human_reviewer":  [],
        "preliminary_recommendation":    "Insufficient Information",
        "recommendation_reasoning":      "Coordinator did not provide reasoning.",
        "coordinator_confidence":        "Low",
    }

    out = {**defaults, **raw}

    # Ensure list fields are actually lists
    for list_key in ("key_strengths", "key_risks", "conflicts_or_tensions",
                     "critical_missing_information", "questions_for_human_reviewer"):
        if not isinstance(out[list_key], list):
            out[list_key] = []

    # Clamp to valid enum values
    if out["preliminary_recommendation"] not in VALID_RECOMMENDATIONS:
        out["preliminary_recommendation"] = "Insufficient Information"

    if out["coordinator_confidence"] not in VALID_CONFIDENCE:
        out["coordinator_confidence"] = "Low"

    # If any agent failed, confidence must not be High
    if any_failed and out["coordinator_confidence"] == "High":
        out["coordinator_confidence"] = "Medium"

    return out
