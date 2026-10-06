import json
import os

demo_dir = 'backend/app/data/cached_demo_results'
for fname in ['strong_crispr.json', 'budget_error_chatbot.json', 'mixed_blockchain.json']:
    fpath = os.path.join(demo_dir, fname)
    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        result = data.get('result', {})
        scoring = result.get('scoring', {})
        print(f'OK {fname}: id={data.get("id")}, score={scoring.get("overall_score")}, band={scoring.get("score_band")}')
    except Exception as e:
        print(f'ERR {fname}: {type(e).__name__}: {e}')
