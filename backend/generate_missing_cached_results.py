"""Generate missing cached results for budget_error_chatbot and fix mixed_blockchain."""
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

PROPOSALS_DIR = Path("app/data/sample_proposals")
OUTPUT_DIR = Path("app/data/cached_demo_results")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Generate missing results
proposals = [
    {
        "id": "budget_error_chatbot",
        "filename": "budget_error_proposal.txt",
        "title": "AI Mental Health Chatbot",
        "description": "Good proposal but budget math error",
    },
    {
        "id": "mixed_blockchain",
        "filename": "mixed_proposal.txt",
        "title": "Blockchain Supply Chain Platform",
        "description": "Mixed proposal with vague technical details",
    },
]

for sample in proposals:
    proposal_path = PROPOSALS_DIR / sample["filename"]
    proposal_text = proposal_path.read_text(encoding="utf-8")
    
    print(f"Running: {sample['title']}...")
    start = time.perf_counter()
    
    result = run_full_evaluation(proposal_text, sample["filename"], None, None)
    elapsed = time.perf_counter() - start
    
    scoring = result.get("scoring", {})
    print(f"  Completed in {elapsed:.1f}s: N={scoring.get('novelty_score')}, T={scoring.get('technical_score')}, F={scoring.get('financial_score')}, I={scoring.get('impact_score')}, O={scoring.get('overall_score')}, Band={scoring.get('score_band')}")
    
    cached_result = {
        "id": sample["id"],
        "title": sample["title"],
        "description": sample["description"],
        "filename": sample["filename"],
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "pipeline_time_seconds": round(elapsed, 1),
        "result": decimal_to_float(result),
    }
    
    output_path = OUTPUT_DIR / f"{sample['id']}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(cached_result, f, indent=2, ensure_ascii=False)
    
    print(f"  Saved to {output_path}\n")

print("Done!")
