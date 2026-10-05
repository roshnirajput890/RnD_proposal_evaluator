# Implementation Plan: Demo Mode Feature

## Overview
Complete the Demo Mode feature for the R&D proposal evaluation system. Three cached sample proposals (strong_crispr.json, budget_error_chatbot.json, mixed_blockchain.json) should load instantly via a dropdown on the New Analysis page, display results with a "Demo result — precomputed" badge, and the real upload-and-analyze path remains fully unchanged.

## Current State
- 3 cached JSON files exist at `backend/app/data/cached_demo_results/`
- No demo API endpoints exist yet
- NewAnalysis.jsx has no demo dropdown or badge component
- History view has no demo label
- mixed_blockchain.json has encoding but loads correctly in both UTF-8 and Latin-1

---

## Implementation Tasks

### 1. Fix mixed_blockchain.json encoding (Preventative)
Re-read mixed_blockchain.json in UTF-8 and re-save cleanly to ensure consistent encoding across all demo JSON files.

**Files:**
- `backend/app/data/cached_demo_results/mixed_blockchain.json`

**Verify:**
```
python -c "
import json
with open('backend/app/data/cached_demo_results/mixed_blockchain.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
print(f\"Parsed successfully: {data.get('id')} - {data.get('title')}\")
"
```

---

### 2. Add demo API endpoint: GET /api/evaluations/demo/{id}
Create a new route in `backend/app/routes/evaluations.py` that serves cached demo results. The endpoint must return the exact same JSON structure as a real evaluation (from the cached file's `result` key merged with metadata). This ensures the frontend UI components consume demo results identically to real results.

**Design Decision:** The demo endpoint will:
- Load the cached JSON file from `backend/app/data/cached_demo_results/{id}.json`
- Extract the `result` key (contains all agent outputs + coordinator)
- Merge it with metadata (`id`, `filename`, `generated_at`, `pipeline_time_seconds`)
- Return with a `is_demo_result: true` flag so frontend can render the badge
- Return HTTP 404 if the demo file doesn't exist

**Files:**
- `backend/app/routes/evaluations.py` — add new endpoint after the existing `fetch_evaluation` endpoint

**Code Insertion Point:**
Insert before the final `@router.get("/analytics", ...)` endpoint.

**Endpoint Response Shape:**
```json
{
  "id": "strong_crispr",
  "filename": "strong_proposal.txt",
  "is_demo_result": true,
  "generated_at": "2026-10-05 01:39:37",
  "pipeline_time_seconds": 543.5,
  "analysis": { ... },
  "full_result": { ... },
  "coordinator_summary": { ... },
  "novelty_score": 3,
  "technical_score": 4,
  "financial_score": 3,
  "impact_score": 5,
  "overall_score": 3.8,
  "score_band": "Revise and Resubmit",
  "preliminary_recommendation": "Revise and Resubmit"
}
```

**Verify:**
```
curl http://localhost:8000/api/evaluations/demo/strong_crispr
curl http://localhost:8000/api/evaluations/demo/budget_error_chatbot
curl http://localhost:8000/api/evaluations/demo/mixed_blockchain
curl http://localhost:8000/api/evaluations/demo/nonexistent
```
All three should return 200 with valid JSON; nonexistent should return 404.

---

### 3. Update NewAnalysis.jsx to add demo dropdown and demo result view
Add a "Try a sample proposal" section with:
- A dropdown to select from 3 demo proposals (strong_crispr, budget_error_chatbot, mixed_blockchain)
- A "Load demo" button that fetches the demo result
- Display results using existing UI components (ScoreBreakdown, CoordinatorPanel, etc.)
- A visible "Demo result — precomputed" badge at the top of results
- Ensure real upload flow is unchanged

**Design Decision:** 
- Demo section will appear ABOVE the upload area, as a separate subsection under a new label "Demo & Testing"
- Demo dropdown hardcodes the 3 available proposals with labels (e.g., "CRISPR Viral Detection (Strong)" → strong_crispr)
- On demo load, results display in the same "analysisResult" state so existing display logic works
- Add `isDemoResult` flag to analysisResult to trigger badge rendering
- Do NOT modify the real analysis or saving logic

**Files:**
- `frontend/src/views/NewAnalysis.jsx`

**Changes:**
- Add state: `isDemoResult` (boolean)
- Add function: `handleDemoSelect(demoId)` that fetches `/api/evaluations/demo/{id}`
- Add JSX section before upload area with demo dropdown + button
- Modify result display area to show "Demo result — precomputed" badge when `isDemoResult=true`
- Reset demo flag when user selects a real file

**Verify:**
```bash
cd frontend
npm run dev
# Navigate to New Analysis page
# Confirm dropdown appears with 3 options
# Load each demo proposal and confirm results display
# Confirm demo results show badge
# Confirm real file upload still works
# Confirm badge disappears when switching to real upload
```

---

### 4. Update History.jsx to label demo results
Add a "Demo" badge or label in the History list for results that came from demo. When rendering history rows, check if the result contains demo metadata and add a visible label.

**Design Decision:**
- Only demo results that were **saved to the database** will appear in History (the current workflow saves demo results after viewing, if user clicks "Save review")
- Add a "Demo" tag next to the date in each history row that matches a demo proposal (by checking filename or id)
- Alternative simpler approach: Check if `pipeline_time_seconds` matches a known demo result's time, or add a `is_demo_result` column to DB
- For now: Add inline visual check — if filename matches a demo file name (strong_proposal.txt, budget_error_proposal.txt, mixed_proposal.txt), add "Demo" label

**Files:**
- `frontend/src/views/History.jsx`

**Changes:**
- Add helper function: `isDemoFilename(filename)` checking for demo proposal file names
- In the history row rendering, after the filename, add a "Demo" badge if `isDemoFilename(filename) === true`

**Verify:**
```bash
# After completing step 3, manually click "Save review" on a demo result
# Reload frontend, navigate to History
# Confirm saved demo result shows up with a "Demo" label/badge
```

---

## Verification Steps (All Together)

### Full Integration Test:
1. **Start backend:** `python -m uvicorn app.main:app --reload` (if not already running)
2. **Start frontend:** `npm run dev`
3. **Test demo endpoint directly:**
   ```bash
   curl http://localhost:8000/api/evaluations/demo/strong_crispr | jq '.id, .is_demo_result, .overall_score'
   ```
4. **Test NewAnalysis demo dropdown:**
   - Navigate to /new-analysis
   - Confirm demo section appears above upload area
   - Select each of the 3 demos and load them
   - Confirm results display with badge
   - Confirm scores match cached JSON
5. **Test real upload still works:**
   - Upload a test PDF
   - Confirm pipeline runs (not cached)
   - Confirm no demo badge appears
6. **Test History labels:**
   - Save a demo result (click Save review on a demo)
   - Go to History
   - Confirm demo result shows "Demo" label
   - Confirm real results show no label

---

## Files Modified
- `backend/app/routes/evaluations.py` — add GET /api/evaluations/demo/{id}
- `backend/app/data/cached_demo_results/mixed_blockchain.json` — re-save with clean UTF-8 encoding
- `frontend/src/views/NewAnalysis.jsx` — add demo dropdown + badge
- `frontend/src/views/History.jsx` — add demo label in list

## Files NOT Modified
- Real analysis pipeline (orchestrator.py, agents, etc.)
- Database schema
- API endpoints for real analysis
- Upload and analyze flow

---

## Edge Cases Handled
- Demo file not found → 404 from backend
- User switches between demo and real file → UI state resets correctly
- Demo results saved to DB → History labels them appropriately
- Concurrent demo loads → Each returns independent cached data
- Frontend refresh during demo load → State preserved

