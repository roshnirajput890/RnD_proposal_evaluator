"""
rubrics.py — Per-agent scoring rubrics.

Each agent evaluates one dimension on a 1–5 integer scale.
The rubric describes what 1, 3, and 5 look like for that dimension,
giving the LLM a concrete anchor for its score.

Public API:
    RUBRICS          — dict[agent_name -> RubricEntry]
    get_rubric_block(agent_name) -> str
        Returns the formatted rubric text ready to inject into a system prompt.

Dimension assignment (matches scoring.py weights):
    general_analysis → Novelty    (the 'main_idea' and 'title' dimension)
    technical        → Technical  (future agent; rubric included for completeness)
    financial        → Financial  (future agent)
    impact           → Impact     (future agent)

For Brick 8 only general_analysis is active. The other three rubrics are
defined here so scoring.py can reference them and so future agents can
import and inject them without changes to this file.
"""
from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class RubricEntry:
    dimension: str          # human-readable dimension name
    description: str        # one-line description of what is being scored
    score_1: str            # what a score of 1 looks like
    score_3: str            # what a score of 3 looks like
    score_5: str            # what a score of 5 looks like
    extra_notes: str = ""   # additional guidance injected after the table


RUBRICS: Dict[str, RubricEntry] = {

    "general_analysis": RubricEntry(
        dimension    = "Proposal Structure",
        description  = (
            "How clearly and completely does the proposal articulate its core elements: "
            "title/topic, main idea, problem being solved, and proposed solution? "
            "This is a structural completeness check, not a novelty judgement."
        ),
        score_1 = (
            "The proposal is vague or incomplete. Key elements (title, problem, solution) "
            "are missing or too brief to evaluate meaningfully."
        ),
        score_3 = (
            "The proposal covers most core elements but some are underdeveloped. "
            "The problem or solution is stated but not clearly argued."
        ),
        score_5 = (
            "The proposal clearly and completely states title/topic, main idea, "
            "the problem it addresses, and its proposed solution. All four elements "
            "are specific, distinct, and well-argued."
        ),
        extra_notes = (
            "NOTE: Novelty evaluation (comparison against existing literature) is "
            "handled by a separate agent. Do not score novelty here."
        ),
    ),

    "novelty_agent": RubricEntry(
        dimension    = "Novelty",
        description  = (
            "How novel and original is the proposed idea relative to existing published work? "
            "You have access to a list of retrieved papers from OpenAlex. "
            "You MUST only reference papers from that list — never invent citations. "
            "IMPORTANT: This is a limited automated search (OpenAlex, ~3 queries). "
            "It is NOT exhaustive. Score is capped at 4 — score 5 is not available here "
            "because we cannot confirm novelty from an automated search alone."
        ),
        score_1 = (
            "Retrieved papers show direct, substantial overlap with the proposed idea. "
            "The claimed innovation appears to already exist in published form with "
            "similar methodology and goals."
        ),
        score_3 = (
            "Retrieved papers show related work but the proposed idea has meaningful "
            "differences in approach, context, or application. Some novelty is evident "
            "but the incremental nature limits the claim."
        ),
        score_5 = (
            "SCORE 5 IS NOT AVAILABLE in this agent. Use 4 at most. "
            "The maximum score is 4 because this is a limited automated search."
        ),
        extra_notes = (
            "MANDATORY: Set external_evidence_used to true if any papers were retrieved, "
            "false if the retrieved list is empty. "
            "MANDATORY: State in novelty_confidence_note that this is a limited automated "
            "search, not an exhaustive literature review, and confidence is capped at medium. "
            "MANDATORY: Score must not exceed 4."
        ),
    ),

    "technical": RubricEntry(
        dimension    = "Technical Feasibility",
        description  = (
            "How technically credible, complete, and achievable is the proposed "
            "methodology given current technology and the team's stated capabilities?"
        ),
        score_1 = (
            "The methodology is vague, relies on unproven technology, "
            "or contains fundamental technical errors. No clear development plan exists."
        ),
        score_3 = (
            "The methodology is broadly sound but has gaps: some key technical "
            "risks are unaddressed, the timeline may be optimistic, or the team's "
            "expertise in critical areas is unclear."
        ),
        score_5 = (
            "The methodology is detailed, realistic, and technically rigorous. "
            "Key risks are identified with mitigation strategies. The team has "
            "demonstrated expertise. The development path is clearly laid out."
        ),
    ),

    "financial": RubricEntry(
        dimension    = "Financial Viability",
        description  = (
            "How well-justified is the budget, and how credible is the "
            "commercialisation / sustainability pathway?"
        ),
        score_1 = (
            "Budget is absent, unjustified, or wildly disproportionate to scope. "
            "No commercialisation pathway or sustainability plan is present."
        ),
        score_3 = (
            "Budget is broadly appropriate but some line items are vague. "
            "A commercialisation route exists but relies on unvalidated assumptions."
        ),
        score_5 = (
            "Budget is detailed, justified, and proportionate. "
            "A credible commercialisation plan exists with market evidence, "
            "identified customers, or confirmed partnerships."
        ),
    ),

    "impact": RubricEntry(
        dimension    = "Societal / Strategic Impact",
        description  = (
            "What is the potential breadth and depth of impact — scientific, "
            "economic, societal, or strategic — if the proposal succeeds?"
        ),
        score_1 = (
            "Impact is narrow, speculative, or not meaningfully described. "
            "Benefits would be minimal or confined to a very small group."
        ),
        score_3 = (
            "Moderate impact on a defined community or sector. "
            "Benefits are plausible but not transformative; limited wider reach."
        ),
        score_5 = (
            "High potential for significant, measurable impact at scale — "
            "scientific breakthroughs, substantial economic value, or clear "
            "societal benefit well beyond the immediate project."
        ),
    ),
}


# ── Helper ────────────────────────────────────────────────────────────────────

def get_rubric_block(agent_name: str) -> str:
    """
    Return a formatted rubric block ready to inject into a system prompt.

    Example output:
        SCORING RUBRIC — Novelty (score 1–5)
        ...
        Score 1: ...
        Score 3: ...
        Score 5: ...

        IMPORTANT: ...
    """
    entry = RUBRICS.get(agent_name)
    if not entry:
        return ""

    lines = [
        f"SCORING RUBRIC — {entry.dimension} (score 1–5)",
        f"What you are scoring: {entry.description}",
        "",
        f"Score 1 (Poor):      {entry.score_1}",
        f"Score 3 (Adequate):  {entry.score_3}",
        f"Score 5 (Excellent): {entry.score_5}",
    ]
    if entry.extra_notes:
        lines += ["", entry.extra_notes]

    return "\n".join(lines)
