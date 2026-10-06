"""
scoring.py — Pure-Python weighted scoring service. No LLM calls.

The LLM provides raw 1-5 dimension scores; this module combines them into a
single overall_score and derives a score_band. Keeping the maths here (not in
the LLM prompt) ensures determinism, auditability, and easy weight changes.

PUBLIC API:
    compute_scores(novelty, technical, financial, impact) -> ScoringResult

WEIGHTS (change these constants — nothing else needs to change):
    NOVELTY_WEIGHT   = 0.25
    TECHNICAL_WEIGHT = 0.30
    FINANCIAL_WEIGHT = 0.20
    IMPACT_WEIGHT    = 0.25

SCORE BAND RULES:
    >= 4.0               → "Recommend"
    3.0 – 3.9            → "Revise and Resubmit"
    < 3.0                → "Not Recommended"
    2+ null scores       → "Insufficient Information" (overrides numeric result)

PARTIAL SCORING:
    Null scores are excluded from the average; remaining weights are
    proportionally rescaled to sum to 1.0.
    If all scores are null the overall_score is None and band is
    "Insufficient Information".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ── Weights — named constants, easy to change ─────────────────────────────────
NOVELTY_WEIGHT:   float = 0.25
TECHNICAL_WEIGHT: float = 0.30
FINANCIAL_WEIGHT: float = 0.20
IMPACT_WEIGHT:    float = 0.25

# Sanity-check: weights must sum to 1.0
_WEIGHT_SUM = NOVELTY_WEIGHT + TECHNICAL_WEIGHT + FINANCIAL_WEIGHT + IMPACT_WEIGHT
assert abs(_WEIGHT_SUM - 1.0) < 1e-9, f"Weights must sum to 1.0, got {_WEIGHT_SUM}"

# ── Score band thresholds ─────────────────────────────────────────────────────
_RECOMMEND_THRESHOLD    = 4.0   # >= this → "Recommend"
_REVISE_THRESHOLD       = 3.0   # >= this → "Revise and Resubmit"
                                 # <  this → "Not Recommended"
_INSUF_NULL_COUNT       = 2     # >= this many nulls → "Insufficient Information"

BAND_RECOMMEND = "Recommend"
BAND_REVISE    = "Revise and Resubmit"
BAND_REJECT    = "Not Recommended"
BAND_INSUF     = "Insufficient Information"


@dataclass
class ScoringResult:
    # Input scores (1-5 or None)
    novelty_score:   Optional[int]
    technical_score: Optional[int]
    financial_score: Optional[int]
    impact_score:    Optional[int]

    # Computed
    overall_score: Optional[float]      # rounded to 2dp, or None
    score_band:    str                  # one of the four BAND_* constants
    is_partial:    bool                 # True when at least one score was null
    null_count:    int                  # how many dimension scores were null
    active_weights: dict = field(default_factory=dict)  # rescaled weights used


def compute_scores(
    novelty:   Optional[int],
    technical: Optional[int],
    financial: Optional[int],
    impact:    Optional[int],
) -> ScoringResult:
    """
    Compute overall_score (weighted average) and score_band.

    Null dimension scores are excluded and the remaining weights are
    proportionally rescaled.

    Args:
        novelty, technical, financial, impact — integer 1-5 or None.
            Values outside 1-5 are treated as None.

    Returns:
        ScoringResult dataclass.
    """

    def _clean(v: Optional[int]) -> Optional[int]:
        if v is None:
            return None
        try:
            iv = int(v)
            return iv if 1 <= iv <= 5 else None
        except (TypeError, ValueError):
            return None

    n = _clean(novelty)
    t = _clean(technical)
    f = _clean(financial)
    i = _clean(impact)

    all_scores   = [n, t, f, i]
    null_count   = sum(1 for s in all_scores if s is None)
    is_partial   = null_count > 0

    # Force "Insufficient Information" if too many nulls
    if null_count >= _INSUF_NULL_COUNT:
        return ScoringResult(
            novelty_score=n, technical_score=t,
            financial_score=f, impact_score=i,
            overall_score=None,
            score_band=BAND_INSUF,
            is_partial=True,
            null_count=null_count,
            active_weights={},
        )

    # Build (score, weight) pairs for non-null scores only
    pairs = [
        (n, NOVELTY_WEIGHT),
        (t, TECHNICAL_WEIGHT),
        (f, FINANCIAL_WEIGHT),
        (i, IMPACT_WEIGHT),
    ]
    active = [(score, w) for score, w in pairs if score is not None]

    if not active:
        # All null — should be caught above, but defensive
        return ScoringResult(
            novelty_score=n, technical_score=t,
            financial_score=f, impact_score=i,
            overall_score=None,
            score_band=BAND_INSUF,
            is_partial=True,
            null_count=4,
            active_weights={},
        )

    # Proportionally rescale weights so they sum to 1.0
    total_active_weight = sum(w for _, w in active)
    rescaled = [(score, w / total_active_weight) for score, w in active]

    # Weighted average
    overall = sum(score * w for score, w in rescaled)
    overall = round(overall, 2)

    # Band derivation
    if overall >= _RECOMMEND_THRESHOLD:
        band = BAND_RECOMMEND
    elif overall >= _REVISE_THRESHOLD:
        band = BAND_REVISE
    else:
        band = BAND_REJECT

    # Build active weights map for transparency
    dim_names = ["novelty", "technical", "financial", "impact"]
    raw_weights = [NOVELTY_WEIGHT, TECHNICAL_WEIGHT, FINANCIAL_WEIGHT, IMPACT_WEIGHT]
    scores_list = [n, t, f, i]
    aw = {}
    for dim, score, raw_w in zip(dim_names, scores_list, raw_weights):
        if score is not None:
            aw[dim] = round(raw_w / total_active_weight, 4)

    return ScoringResult(
        novelty_score=n, technical_score=t,
        financial_score=f, impact_score=i,
        overall_score=overall,
        score_band=band,
        is_partial=is_partial,
        null_count=null_count,
        active_weights=aw,
    )


# ── Helper: convert to plain dict for JSON serialisation ──────────────────────

def scoring_result_to_dict(r: ScoringResult) -> dict:
    return {
        "novelty_score":   r.novelty_score,
        "technical_score": r.technical_score,
        "financial_score": r.financial_score,
        "impact_score":    r.impact_score,
        "overall_score":   r.overall_score,
        "score_band":      r.score_band,
        "is_partial":      r.is_partial,
        "null_count":      r.null_count,
        "active_weights":  r.active_weights,
    }



# ── Agent state descriptions for UI ────────────────────────────────────────────

def get_agent_state_description(score: Optional[int], agent_status: str, agent_name: str) -> str:
    """
    Return a human-readable description of an agent's state for display.
    
    Args:
        score: The agent's score (1-5 or None)
        agent_status: "completed", "failed", "error", or other
        agent_name: Name of the agent (e.g., "technical", "financial")
    
    Returns:
        "Scored (X/5)" | "Failed: timeout or parse error" | "Not applicable: no [section]"
    """
    if score is not None:
        return f"Scored ({score}/5)"
    elif agent_status in ("failed", "error"):
        return "Failed: timeout or parse error"
    elif agent_name == "financial":
        return "Not applicable: no budget or financial section found"
    elif agent_name == "technical":
        return "Not applicable: no technical methodology found"
    elif agent_name == "impact":
        return "Not applicable: no impact or objectives section found"
    else:
        return "Not applicable: data unavailable"
