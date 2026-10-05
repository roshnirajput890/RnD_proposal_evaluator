"""
generate_cached_demo_results.py — Generate cached demo results for all sample proposals.

Runs the FULL real pipeline on each sample proposal and saves complete JSON results.
This will take several minutes per proposal.
"""
import json
import time
from pathlib import Path
from decimal import Decimal
from app.services.orchestrator import run_full_evaluation


def decimal_to_float(obj):
    """Convert Decimal objects to float for JSON serialization."""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_float(item) for item in obj]
    return obj

# Sample proposal files
SAMPLE_PROPOSALS = [
    {
        "id": "strong_crispr",
        "filename": "strong_proposal.txt",
        "title": "CRISPR Viral Detection System",
        "description": "Strong proposal with comprehensive details, validated technology, clear budget",
    },
    {
        "id": "mixed_blockchain",
        "filename": "mixed_proposal.txt",
        "title": "Blockchain Supply Chain Platform",
        "description": "Mixed proposal with vague technical details, weak team credentials",
    },
    {
        "id": "budget_error_chatbot",
        "filename": "budget_error_proposal.txt",
        "title": "AI Mental Health Chatbot",
        "description": "Good proposal but budget math error (line items sum to $984k, stated total $750k)",
    },
]

PROPOSALS_DIR = Path("app/data/sample_proposals")
OUTPUT_DIR = Path("app/data/cached_demo_results")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def main():
    print("="*70)
    print("GENERATING CACHED DEMO RESULTS")
    print("="*70)
    print(f"\nThis will run the FULL pipeline on {len(SAMPLE_PROPOSALS)} sample proposals.")
    print("Expected time: ~7-9 minutes per proposal\n")
    
    overall_start = time.perf_counter()
    
    for i, sample in enumerate(SAMPLE_PROPOSALS, 1):
        print(f"\n{'='*70}")
        print(f"[{i}/{len(SAMPLE_PROPOSALS)}] Processing: {sample['title']}")
        print(f"{'='*70}\n")
        
        # Read proposal text
        proposal_path = PROPOSALS_DIR / sample["filename"]
        if not proposal_path.exists():
            print(f"ERROR: File not found: {proposal_path}")
            continue
        
        proposal_text = proposal_path.read_text(encoding="utf-8")
        print(f"Loaded proposal: {len(proposal_text)} characters")
        print(f"Running full evaluation pipeline...\n")
        
        # Run full evaluation
        start = time.perf_counter()
        try:
            result = run_full_evaluation(
                proposal_text=proposal_text,
                filename=sample["filename"],
                model=None,
                timeout=None,
            )
            elapsed = time.perf_counter() - start
            
            print(f"\n[OK] Pipeline completed in {elapsed:.1f}s")
            
            # Show scores
            scoring = result.get("scoring", {})
            print(f"\nScores:")
            print(f"  Novelty:    {scoring.get('novelty_score', 'n/a')}")
            print(f"  Technical:  {scoring.get('technical_score', 'n/a')}")
            print(f"  Financial:  {scoring.get('financial_score', 'n/a')}")
            print(f"  Impact:     {scoring.get('impact_score', 'n/a')}")
            print(f"  Overall:    {scoring.get('overall_score', 'n/a')}")
            print(f"  Band:       {scoring.get('score_band', 'n/a')}")
            
            # Add metadata
            cached_result = {
                "id": sample["id"],
                "title": sample["title"],
                "description": sample["description"],
                "filename": sample["filename"],
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "pipeline_time_seconds": round(elapsed, 1),
                "result": decimal_to_float(result),  # Convert Decimals to float
            }
            
            # Save to JSON
            output_path = OUTPUT_DIR / f"{sample['id']}.json"
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(cached_result, f, indent=2, ensure_ascii=False)
            
            print(f"\n[OK] Saved to: {output_path}")
            
        except Exception as e:
            print(f"\n[ERROR] Pipeline failed: {e}")
            import traceback
            traceback.print_exc()
    
    overall_elapsed = time.perf_counter() - overall_start
    print(f"\n{'='*70}")
    print(f"ALL SAMPLES PROCESSED")
    print(f"{'='*70}")
    print(f"Total time: {overall_elapsed:.1f}s (~{overall_elapsed/60:.1f} minutes)")
    print(f"\nCached results saved to: {OUTPUT_DIR.resolve()}")

if __name__ == "__main__":
    main()
