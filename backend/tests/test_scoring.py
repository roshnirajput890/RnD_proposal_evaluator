"""
Unit tests for services/scoring.py.

Run with:
    cd backend
    .\\venv\\Scripts\\python.exe -m pytest tests/test_scoring.py -v
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.scoring import (
    compute_scores,
    BAND_RECOMMEND, BAND_REVISE, BAND_REJECT, BAND_INSUF,
    NOVELTY_WEIGHT, TECHNICAL_WEIGHT, FINANCIAL_WEIGHT, IMPACT_WEIGHT,
)


# ── Case 1: All four scores present ─────────────────────────────────────────

def test_all_scores_recommend():
    r = compute_scores(novelty=5, technical=4, financial=4, impact=5)
    assert r.novelty_score   == 5
    assert r.technical_score == 4
    assert r.financial_score == 4
    assert r.impact_score    == 5
    assert r.overall_score is not None
    assert r.overall_score >= 4.0
    assert r.score_band == BAND_RECOMMEND
    assert r.is_partial is False
    assert r.null_count == 0


def test_all_scores_revise():
    r = compute_scores(novelty=3, technical=3, financial=3, impact=3)
    assert r.overall_score == 3.0
    assert r.score_band == BAND_REVISE
    assert r.is_partial is False


def test_all_scores_reject():
    r = compute_scores(novelty=1, technical=2, financial=1, impact=2)
    assert r.overall_score is not None
    assert r.overall_score < 3.0
    assert r.score_band == BAND_REJECT


def test_boundary_exactly_40():
    """Score of exactly 4.0 should be Recommend."""
    # With equal 1.0 weight (all present), need sum = 4.0
    # n*0.25 + t*0.30 + f*0.20 + i*0.25 = 4.0
    # Use: 4,4,4,4 → 4.0
    r = compute_scores(novelty=4, technical=4, financial=4, impact=4)
    assert r.overall_score == 4.0
    assert r.score_band == BAND_RECOMMEND


def test_boundary_exactly_30():
    """Score of exactly 3.0 should be Revise."""
    r = compute_scores(novelty=3, technical=3, financial=3, impact=3)
    assert r.overall_score == 3.0
    assert r.score_band == BAND_REVISE


def test_weighted_average_correctness():
    """Verify the weighted average formula is applied correctly."""
    r = compute_scores(novelty=5, technical=5, financial=1, impact=1)
    expected = 5 * NOVELTY_WEIGHT + 5 * TECHNICAL_WEIGHT + 1 * FINANCIAL_WEIGHT + 1 * IMPACT_WEIGHT
    assert abs(r.overall_score - round(expected, 2)) < 0.01


# ── Case 2: One score missing ─────────────────────────────────────────────────

def test_one_null_reweights():
    """With one null, remaining weights rescale to sum to 1.0."""
    r = compute_scores(novelty=None, technical=4, financial=4, impact=4)
    assert r.is_partial is True
    assert r.null_count == 1
    assert r.overall_score is not None
    # Active weights must sum to 1.0
    assert abs(sum(r.active_weights.values()) - 1.0) < 1e-6
    # "novelty" must not appear in active_weights
    assert "novelty" not in r.active_weights
    # With three scores of 4, overall should still be 4.0
    assert r.overall_score == 4.0
    assert r.score_band == BAND_RECOMMEND


def test_one_null_low_scores_still_rejects():
    r = compute_scores(novelty=None, technical=1, financial=2, impact=1)
    assert r.is_partial is True
    assert r.overall_score < 3.0
    assert r.score_band == BAND_REJECT


# ── Case 3: Two scores missing → Insufficient Information ────────────────────

def test_two_nulls_insufficient():
    r = compute_scores(novelty=None, technical=None, financial=4, impact=5)
    assert r.score_band == BAND_INSUF
    assert r.overall_score is None
    assert r.is_partial is True
    assert r.null_count == 2


def test_two_nulls_even_if_remaining_high():
    """Even if remaining scores are 5, 2 nulls must give Insufficient."""
    r = compute_scores(novelty=None, technical=None, financial=5, impact=5)
    assert r.score_band == BAND_INSUF


# ── Case 4: All scores null ───────────────────────────────────────────────────

def test_all_null():
    r = compute_scores(novelty=None, technical=None, financial=None, impact=None)
    assert r.score_band == BAND_INSUF
    assert r.overall_score is None
    assert r.null_count == 4


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_out_of_range_treated_as_null():
    """Scores outside 1-5 must be treated as null."""
    r = compute_scores(novelty=6, technical=0, financial=3, impact=3)
    assert r.novelty_score is None   # 6 is out of range
    assert r.technical_score is None  # 0 is out of range
    assert r.null_count == 2
    assert r.score_band == BAND_INSUF


def test_string_score_treated_as_null():
    r = compute_scores(novelty="high", technical=3, financial=3, impact=3)
    assert r.novelty_score is None
    assert r.null_count == 1
    assert r.is_partial is True


def test_active_weights_sum_to_one_with_one_null():
    r = compute_scores(novelty=None, technical=4, financial=4, impact=4)
    total = sum(r.active_weights.values())
    assert abs(total - 1.0) < 1e-9


if __name__ == "__main__":
    # Allow running directly without pytest
    import traceback
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed, failed = 0, 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except Exception:
            print(f"  FAIL  {fn.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
