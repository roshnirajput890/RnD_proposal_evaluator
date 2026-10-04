"""
budget_calculator.py — Pure Python budget validation (no LLM).

Stage B of the Financial Agent pipeline:
  - Sum extracted budget line items
  - Compare to stated total (if present)
  - Flag mismatches
  - Identify missing cost categories

Uses Decimal for accurate money arithmetic.
"""
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

# Expected budget categories (common R&D cost areas)
EXPECTED_CATEGORIES = {
    "personnel", "salaries", "staff", "labor",
    "equipment", "hardware", "software", "materials",
    "travel", "overhead", "indirect", "facilities",
    "subcontract", "consulting", "other",
}


def validate_budget(
    line_items:   List[Dict[str, Any]],
    stated_total: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Validate extracted budget line items.

    Args:
        line_items: List of {item, amount, category} dicts from LLM extraction
        stated_total: Total budget amount stated in proposal (if found)

    Returns:
        {
            computed_total: Decimal,
            stated_total: Decimal or None,
            mismatch: bool,
            mismatch_amount: Decimal or None,
            mismatch_percent: float or None,
            missing_categories: [str],
            line_item_count: int,
            summary: str
        }
    """
    # Sum line items
    computed = Decimal("0")
    valid_items = 0
    categories_found = set()
    
    for item in line_items:
        amount = item.get("amount")
        category = (item.get("category") or "").lower().strip()
        
        if category:
            categories_found.add(category)
        
        if amount is None:
            continue
            
        try:
            # Convert to Decimal for precise arithmetic
            if isinstance(amount, str):
                # Strip currency symbols and commas
                amount = amount.replace("$", "").replace(",", "").replace("€", "").replace("£", "").strip()
            computed += Decimal(str(amount))
            valid_items += 1
        except (InvalidOperation, ValueError) as exc:
            logger.warning("budget_calculator: invalid amount %r: %s", amount, exc)
            continue
    
    # Convert stated total to Decimal
    stated_dec: Optional[Decimal] = None
    if stated_total is not None:
        try:
            stated_dec = Decimal(str(stated_total))
        except (InvalidOperation, ValueError):
            logger.warning("budget_calculator: invalid stated_total %r", stated_total)
    
    # Check for mismatch
    mismatch = False
    mismatch_amt: Optional[Decimal] = None
    mismatch_pct: Optional[float] = None
    
    if stated_dec is not None and computed > 0:
        diff = abs(computed - stated_dec)
        # Flag mismatch if difference > 1% or > $1000
        threshold_pct = Decimal("0.01") * stated_dec
        threshold_abs = Decimal("1000")
        
        if diff > max(threshold_pct, threshold_abs):
            mismatch = True
            mismatch_amt = diff
            if stated_dec != 0:
                mismatch_pct = float((diff / stated_dec) * 100)
    
    # Identify missing categories
    missing_cats = []
    for cat in EXPECTED_CATEGORIES:
        if not any(cat in found for found in categories_found):
            missing_cats.append(cat)
    
    # Generate summary
    if valid_items == 0:
        summary = "No valid budget line items found."
    elif stated_dec is None:
        summary = f"Computed total: ${computed:,.2f} from {valid_items} line items. No stated total to compare."
    elif mismatch:
        summary = (
            f"Budget mismatch: Computed ${computed:,.2f}, stated ${stated_dec:,.2f}. "
            f"Difference: ${mismatch_amt:,.2f} ({mismatch_pct:.1f}%)."
        )
    else:
        summary = f"Budget sums correctly: ${computed:,.2f} matches stated total."
    
    return {
        "computed_total": computed,
        "stated_total": stated_dec,
        "mismatch": mismatch,
        "mismatch_amount": mismatch_amt,
        "mismatch_percent": mismatch_pct,
        "missing_categories": missing_cats[:5],  # Top 5 most obviously missing
        "line_item_count": valid_items,
        "summary": summary,
    }
