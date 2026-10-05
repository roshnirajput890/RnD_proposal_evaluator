import json, time
from pathlib import Path
from decimal import Decimal
from app.services.orchestrator import run_full_evaluation

def decimal_to_float(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_float(item) for item in obj]
    return obj

# Run the third proposal
proposal_path = Path('app/data/sample_proposals/budget_error_proposal.txt')
proposal_text = proposal_path.read_text(encoding='utf-8')
print(f'Running pipeline on {proposal_path.name}...')

result = run_full_evaluation(proposal_text, proposal_path.name, None, None)
output_dir = Path('app/data/cached_demo_results')
output_dir.mkdir(parents=True, exist_ok=True)

cached = {
    'id': 'budget_error_chatbot',
    'title': 'AI Mental Health Chatbot',
    'description': 'Good proposal but budget math error',
    'filename': 'budget_error_proposal.txt',
    'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    'result': decimal_to_float(result),
}

output_path = output_dir / 'budget_error_chatbot.json'
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(cached, f, indent=2, ensure_ascii=False)

print(f'Saved to {output_path}')
scoring = result.get('scoring', {})
print(f'Scores: N={scoring.get("novelty_score")}, T={scoring.get("technical_score")}, F={scoring.get("financial_score")}, I={scoring.get("impact_score")}, Overall={scoring.get("overall_score")}')
