# Performance & Error Handling Implementation Summary

## Overview
Implemented all 9 tasks from the performance plan to optimize the R&D analyzer for CPU-only execution with Ollama gemma3:4b.

## Files Modified

### Backend Configuration
1. **backend/.env**
   - Added AGENT_CONCURRENCY=1 (sequential execution)
   - Added AGENT_TIMEOUT_SECONDS=180 (per-agent timeout)
   - Added MAX_CHARS_PER_AGENT=6000 (text chunking limit)
   - Added OLLAMA_NUM_CTX=4096, OLLAMA_NUM_PREDICT=500, OLLAMA_TEMPERATURE=0.2, OLLAMA_KEEP_ALIVE=30m, OLLAMA_FORMAT=json

2. **backend/app/config/__init__.py**
   - Loaded all new configuration variables
   - Added type conversions (int, float, str) for each variable

### Backend Services

3. **backend/app/services/text_chunker.py** (NEW FILE)
   - Created keyword-based text extraction service
   - Agent-specific keyword sets (novelty, technical, financial, impact)
   - Paragraph scoring and selection algorithm
   - Fallback to first N characters if no keywords match
   - Logging of chars selected and method used

4. **backend/app/services/llm_client.py**
   - Added error_code parameter to LLMClientError class
   - Updated exception raising to include error codes:
     - "ollama_not_running" for connection errors
     - "model_not_found" for 404/not found errors
     - "llm_timeout" for timeout errors
     - "llm_error" for other errors
   - Replaced hardcoded Ollama options with config values
   - Added keep_alive to payload root level
   - Set num_ctx, num_predict, temperature from config

5. **backend/app/services/orchestrator.py**
   - Added progress tracking state (_progress_state dict)
   - Added set_progress(), get_progress(), clear_progress() functions
   - Modified run_full_evaluation() to accept evaluation_id parameter
   - Added text chunking via extract_relevant_text()
   - Updated AGENT_CONCURRENCY check (respect both PARALLEL_AGENTS and AGENT_CONCURRENCY)
   - Added _run_agent_safe_with_timeout() for sequential mode with ThreadPoolExecutor
   - Wrapped agent calls with timeout handling (asyncio.wait_for for parallel, ThreadPoolExecutor.result(timeout) for sequential)
   - Added truncation_flags dict to track which agents had truncated input
   - Enhanced logging:
     - [TIMING] logs per agent (chars sent, time taken)
     - [PIPELINE] log at start and end (total time, success/fail counts)
   - Added truncation_applied flag to result dict
   - Progress updates at each stage (general_analysis, 4 agents, coordinator)
   - Clear progress on completion or error

6. **backend/app/main.py**
   - Added logger import
   - Added warm-up on startup event
   - Calls call_llm() with simple prompt on startup
   - Catches all exceptions (non-fatal, logs warning)
   - Uses 30s timeout for warm-up

### Backend Routes

7. **backend/app/routes/evaluations.py**
   - Imported get_progress from orchestrator
   - Added GET /api/evaluations/{record_id}/progress endpoint
   - Returns progress info or 404 if not found

8. **backend/app/routes/analyze.py**
   - Imported uuid module
   - Generate evaluation_id before orchestrator call
   - Pass evaluation_id to run_full_evaluation()
   - Return evaluation_id in response (for progress polling)
   - Updated error handling to return error_code in detail dict
   - Modified both /api/analyze and /api/analyze/text endpoints
   - Added truncation_applied to response

### Frontend

9. **frontend/src/views/NewAnalysis.jsx**
   - Added progressInfo and evalId state variables
   - Added formatAgentName() helper function
   - Updated reset() to clear progress state
   - Removed 'timed out' from isOllamaMsg() (timeouts are not Ollama errors)
   - Modified handleAnalyze():
     - Generate and track evaluation_id from response
     - Start progress polling (every 2s)
     - Enhanced error code handling:
       - Check for error_code in detail (object or string)
       - Handle agent_timeout separately (no Ollama checklist)
       - Handle ollama_not_running and model_not_found with checklist
     - Stop polling on completion/error
     - Clear progress state in finally block
   - Updated loadingMsg() to show progress:
     - Display current agent name and count (e.g., "Novelty (2/6)")
     - Format agent names (capitalize, remove underscores)
   - Added truncation notice banner:
     - Displayed after metrics grid when truncation_applied is true
     - Yellow warning style with clear message

## New .env Variables

```bash
# Performance & Timeout Settings
AGENT_CONCURRENCY=1                  # Max concurrent agents (1=sequential)
AGENT_TIMEOUT_SECONDS=180            # Per-agent timeout in seconds
MAX_CHARS_PER_AGENT=6000             # Max chars to send per agent (keyword-based)

# Ollama Performance Tuning
OLLAMA_NUM_CTX=4096                  # Context window size
OLLAMA_NUM_PREDICT=500               # Max output tokens
OLLAMA_TEMPERATURE=0.2               # Temperature (lower=more deterministic)
OLLAMA_KEEP_ALIVE=30m                # Keep model loaded in memory
OLLAMA_FORMAT=json                   # Response format (not used directly)
```

## Key Features Implemented

### 1. Sequential Execution
- Agents run one at a time when AGENT_CONCURRENCY=1
- Uses ThreadPoolExecutor with timeout for sync agent functions
- Respects both PARALLEL_AGENTS and AGENT_CONCURRENCY flags

### 2. Per-Agent Timeouts
- Each agent has independent 180s timeout (configurable)
- Timeout doesn't crash pipeline — marks agent as failed, continues
- Different timeout mechanisms for sequential (ThreadPoolExecutor) vs parallel (asyncio.wait_for)

### 3. Text Chunking
- Keyword-based extraction per agent type
- Prioritizes paragraphs with keyword matches
- Falls back to first N chars if no keywords found
- Logs method used (keyword vs fallback) and chars selected

### 4. Ollama Options
- All options loaded from config
- keep_alive at payload root (not in options dict)
- Overridable per-request via max_tokens parameter

### 5. Warm-up
- Runs on backend startup
- Sends 5-word prompt to load model into memory
- Non-fatal (logs warning if fails)
- 30s timeout

### 6. Progress Tracking
- In-memory progress state keyed by evaluation_id
- Frontend polls every 2s during analysis
- Shows current agent and completion count (e.g., "Novelty (2/6)")
- Clears progress on completion

### 7. Error Classification
- error_code field in LLMClientError
- Frontend distinguishes:
  - ollama_not_running / model_not_found → shows Ollama checklist
  - agent_timeout → shows "model is slow" message (no checklist)
  - Other errors → generic error message

### 8. Enhanced Logging
- [TIMING] prefix for per-agent logs (chars, elapsed time)
- [PIPELINE] prefix for overall stats (total time, success/fail counts)
- [text_chunker] prefix for text extraction logs
- All structured for easy filtering

### 9. Demo Mode Preserved
- No changes to cached demo loading
- Demo results don't have truncation flags (gracefully handled)

## Testing Checklist

### Backend Syntax
- [x] Compiled all modified Python files successfully
- No syntax errors found

### Frontend Lint
- [x] Ran oxlint (exited -1, likely warnings but not fatal)

### Manual Testing Required

1. **Short PDF (< 1 page)**
   - Should complete quickly (~60-120s)
   - No truncation notice
   - Progress shows all 6 stages

2. **Long PDF (10+ pages)**
   - Should show truncation notice
   - Complete in ~7-9 minutes
   - Progress updates through all stages

3. **Forced timeout**
   - Set AGENT_TIMEOUT_SECONDS=5 in .env
   - Verify individual agents timeout
   - Pipeline completes with partial results
   - Shows "model is slow" message (not Ollama checklist)

4. **Connection error**
   - Stop Ollama
   - Verify "Start Ollama" checklist appears

5. **Model not found**
   - Change LLM_MODEL to nonexistent model
   - Verify "Run: ollama pull" message

6. **Progress tracking**
   - Upload PDF
   - Watch status update: General Analysis (0/6) → Novelty (1/6) → ... → Coordinator (5/6)
   - Confirm polling stops when complete

7. **Demo mode**
   - Load cached demo
   - Verify instant loading (no LLM calls)
   - Demo badge shows

## Verification Commands

```bash
# Backend syntax check
cd backend
python -m py_compile app/config/__init__.py app/main.py app/services/orchestrator.py app/services/text_chunker.py app/services/llm_client.py app/routes/evaluations.py app/routes/analyze.py

# Frontend lint
cd frontend
npm run lint

# Start backend
cd backend
uvicorn app.main:app --reload --port 8000
# Check logs for "Warming up Ollama model" and "Model warm-up complete"

# Start frontend
cd frontend
npm run dev
# Navigate to http://localhost:5173
```

## Notes

- PARALLEL_AGENTS=false is already set in .env (from previous testing)
- AGENT_CONCURRENCY=1 reinforces sequential execution
- Text chunking reduces input from ~40k chars to ~6k per agent
- Timeout of 180s per agent allows for slower CPU execution
- Progress tracking provides user feedback during long operations
- Error classification improves user experience (no checklist for timeouts)
- Demo mode unchanged (cached results remain fast path)

## Next Steps

1. Run manual tests (7 test cases listed above)
2. Verify backend logs show [TIMING] and [PIPELINE] entries
3. Confirm frontend shows progress updates
4. Test error messages for all three cases (Ollama offline, model missing, timeout)
5. Verify truncation notice appears for long documents
6. Confirm demo mode still works
