"""
test_budget_calculator.py — Unit tests for budget_calculator.py

Tests the pure Python budget validation logic (no LLM needed).
"""
from decimal import Decimal
from app.services.budget_calculator import validate_budget


def test_empty_budget():
    """Test with no line items."""
    result = validate_budget([], stated_total=None)
    assert result["computed_total"] == Decimal("0")
    assert result["stated_total"] is None
    assert result["mismatch"] is False
    assert result["line_item_count"] == 0
    assert "No valid budget line items" in result["summary"]


def test_simple_sum():
    """Test correct sum without stated total."""
    line_items = [
        {"item": "Salaries", "amount": 50000, "category": "personnel"},
        {"item": "Equipment", "amount": 10000, "category": "equipment"},
        {"item": "Travel", "amount": 5000, "category": "travel"},
    ]
    result = validate_budget(line_items, stated_total=None)
    assert result["computed_total"] == Decimal("65000")
    assert result["stated_total"] is None
    assert result["mismatch"] is False
    assert result["line_item_count"] == 3
    assert "No stated total" in result["summary"]


def test_matching_total():
    """Test when computed matches stated total."""
    line_items = [
        {"item": "Salaries", "amount": 50000, "category": "personnel"},
        {"item": "Equipment", "amount": 10000, "category": "equipment"},
    ]
    result = validate_budget(line_items, stated_total=60000)
    assert result["computed_total"] == Decimal("60000")
    assert result["stated_total"] == Decimal("60000")
    assert result["mismatch"] is False
    assert result["line_item_count"] == 2
    assert "matches stated total" in result["summary"]


def test_mismatch_detected():
    """Test when computed differs significantly from stated total."""
    line_items = [
        {"item": "Salaries", "amount": 50000, "category": "personnel"},
        {"item": "Equipment", "amount": 10000, "category": "equipment"},
    ]
    result = validate_budget(line_items, stated_total=100000)
    assert result["computed_total"] == Decimal("60000")
    assert result["stated_total"] == Decimal("100000")
    assert result["mismatch"] is True
    assert result["mismatch_amount"] == Decimal("40000")
    assert result["mismatch_percent"] == 40.0
    assert "Budget mismatch" in result["summary"]


def test_string_amounts_with_currency():
    """Test parsing amounts with currency symbols and commas."""
    line_items = [
        {"item": "Salaries", "amount": "$50,000", "category": "personnel"},
        {"item": "Equipment", "amount": "€10000", "category": "equipment"},
        {"item": "Travel", "amount": "£5,000.50", "category": "travel"},
    ]
    result = validate_budget(line_items, stated_total=65000.50)
    assert result["computed_total"] == Decimal("65000.50")
    assert result["line_item_count"] == 3
    assert result["mismatch"] is False


def test_missing_categories():
    """Test detection of missing budget categories."""
    line_items = [
        {"item": "Salaries", "amount": 50000, "category": "personnel"},
    ]
    result = validate_budget(line_items, stated_total=50000)
    missing = result["missing_categories"]
    assert "equipment" in missing
    assert "travel" in missing
    assert len(missing) <= 5  # Capped at top 5


def test_invalid_amounts_skipped():
    """Test that invalid amounts are skipped gracefully."""
    line_items = [
        {"item": "Salaries", "amount": 50000, "category": "personnel"},
        {"item": "Bad", "amount": "not-a-number", "category": "other"},
        {"item": "Equipment", "amount": None, "category": "equipment"},
        {"item": "Travel", "amount": 5000, "category": "travel"},
    ]
    result = validate_budget(line_items, stated_total=None)
    assert result["computed_total"] == Decimal("55000")
    assert result["line_item_count"] == 2  # Only valid ones counted


def test_small_mismatch_ignored():
    """Test that tiny mismatches (< 1% and < $1000) are not flagged."""
    line_items = [
        {"item": "Salaries", "amount": 100000, "category": "personnel"},
    ]
    # Difference of $500 on $100,000 = 0.5% → should not be flagged
    result = validate_budget(line_items, stated_total=100500)
    assert result["mismatch"] is False


if __name__ == "__main__":
    # Simple test runner
    import sys
    tests = [
        test_empty_budget,
        test_simple_sum,
        test_matching_total,
        test_mismatch_detected,
        test_string_amounts_with_currency,
        test_missing_categories,
        test_invalid_amounts_skipped,
        test_small_mismatch_ignored,
    ]
    
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"✓ {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"✗ {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: Unexpected error: {e}")
            failed += 1
    
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
