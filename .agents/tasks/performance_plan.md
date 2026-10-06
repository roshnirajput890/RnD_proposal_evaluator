# Implementation Plan: Performance & Error Handling Fix

## Context Summary

The R&D analyzer runs a multi-agent pipeline (general_analysis → 4 scoring agents → scoring.py → coordinator) that currently times out after 500 seconds on CPU-only hardware with Ollama gemma3:4b. The system currently supports optional parallel execution (PARALLEL_AGENTS flag), but testing showed parallel was slower than sequential on this hardware.

**Current architecture:**
- Backend: FastAPI + Python, orchestrator in `backend/app/services/orchestrator.py`
- LLM client: `backend/app/services/llm_client.py` using Ollama HTTP API
- Agents: general_analysis + 4 domain agents (novelty, technical, financial, impact) + coordinator
- Config: `backend/app/config/__init__.py` loads from `backend/.env`
- Frontend: React + Vite, main upload/analysis view in `frontend/src/views/NewAnalysis.jsx`

**Key findings from code review:**
- `orchestrator.py` already has sequential/parallel execution toggle via `PARALLEL_AGENTS`
- Parallel mode uses asyncio.Semaphore(2) with max 2 concurrent agents
- Sequential mode calls agents one-by-one in sync functions wrapped in executor
- No per-agent timeout currently; relies on REQUEST_TIMEOUT_SECONDS (180s) global
- LLM client already has error classification (ConnectionRefusedError, TimeoutException, 404 model not found)
- Agents call `call_llm_json()` which handles JSON parsing + retries
- No warm-up currently; model loads on first request
- No text chunking or keyword selection; full proposal text sent to all agents (truncated at MAX_INPUT_CHARS=40000)
- Frontend shows generic "analyzing" spinner; no per-agent progress
- Demo mode already working with cached results in `backend/app/data/cached_demo_results/`

---

## Implementation Plan

- [ ] 1. **Add new config variables to backend/app/config/__init__.py and backend/.env**
      
      Add to `.env`:
      ```
      AGENT_CONCURRENCY=1
      AGENT_TIMEOUT_SECONDS=180
      MAX_CHARS_PER_AGENT=6000
      OLLAMA_NUM_CTX=4096
      OLLAMA_NUM_PREDICT=500
      OLLAMA_TEMPERATURE=0.2
      OLLAMA_KEEP_ALIVE=30m
      OLLAMA_FORMAT=json
      ```
      
      Add to `config/__init__.py`:
      ```python
      AGENT_CONCURRENCY: int = int(os.getenv("AGENT_CONCURRENCY", "1"))
      AGENT_TIMEOUT_SECONDS: float = float(os.getenv("AGENT_TIMEOUT_SECONDS", "180"))
      MAX_CHARS_PER_AGENT: int = int(os.getenv("MAX_CHARS_PER_AGENT", "6000"))
      OLLAMA_NUM_CTX: int = int(os.getenv("OLLAMA_NUM_CTX", "4096"))
      OLLAMA_NUM_PREDICT: int = int(os.getenv("OLLAMA_NUM_PREDICT", "500"))
      OLLAMA_TEMPERATURE: float = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))
      OLLAMA_KEEP_ALIVE: str = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
      OLLAMA_FORMAT: str = os.getenv("OLLAMA_FORMAT", "json")
      ```
      
      **Files:** `backend/.env`, `backend/app/config/__init__.py`
      
      **Verify:** Run `python -c "from app.config import AGENT_TIMEOUT_SECONDS, MAX_CHARS_PER_AGENT, OLLAMA_NUM_CTX; print(AGENT_TIMEOUT_SECONDS, MAX_CHARS_PER_AGENT, OLLAMA_NUM_CTX)"` from backend directory — should print `180.0 6000 4096`

- [ ] 2. **Create text_chunker.py service for keyword-based text extraction**
      
      Create `backend/app/services/text_chunker.py` with:
      - Function `extract_relevant_text(full_text: str, agent_name: str, max_chars: int) -> dict` returning `{"text": str, "truncated": bool, "method": str}`
      - Keyword dictionaries for each agent:
        - novelty: abstract, introduction, problem, innovation, related work, prior art, novelty, contribution, literature, state of the art
        - technical: methodology, approach, architecture, requirements, hardware, software, design, implementation, technology, stack, feasibility, resources
        - financial: budget, cost, funding, total, Rs, INR, $, price, expense, expenditure, allocation, financial, economic
        - impact: objectives, outcomes, beneficiaries, impact, benefits, results, goals, deliverables, social, economic impact, sustainability
      - Search algorithm: find all paragraphs containing any keyword (case-insensitive), collect up to max_chars, prioritize paragraphs with more keyword matches
      - Fallback: if no keywords match, return first max_chars with method="fallback"
      - Log: `logger.info("[text_chunker] %s: %d chars selected via %s (truncated=%s)", agent_name, len(text), method, truncated)`
      
      **Files:** `backend/app/services/text_chunker.py` (new)
      
      **Verify:** Write unit test or quick script: `extract_relevant_text("Budget: Rs 10 lakh. Cost breakdown...", "financial", 100)` should return dict with "Budget: Rs 10 lakh" and method="keyword"

- [ ] 3. **Modify orchestrator.py to use AGENT_CONCURRENCY and per-agent timeouts**
      
      Changes to `backend/app/services/orchestrator.py`:
      - Import `AGENT_CONCURRENCY, AGENT_TIMEOUT_SECONDS, MAX_CHARS_PER_AGENT` from config
      - Import `extract_relevant_text` from text_chunker
      - Modify condition: `if AGENT_CONCURRENCY > 1 and PARALLEL_AGENTS:` (respect both flags)
      - Update `_run_agents_parallel()`: change `Semaphore(2)` to `Semaphore(AGENT_CONCURRENCY)`
      - Modify agent wrapper `_run_agent_safe()`:
        - Extract relevant text before calling agent: `chunk = extract_relevant_text(proposal_text, agent_display_name, MAX_CHARS_PER_AGENT)`
        - Pass `chunk["text"]` to agent instead of full proposal_text
        - Wrap agent call with timeout: `result = asyncio.wait_for(loop.run_in_executor(...), timeout=AGENT_TIMEOUT_SECONDS)` for parallel mode
        - For sequential mode, use threading timeout or time.time() check (note: agents are sync functions, so asyncio.wait_for needs executor wrapper)
        - Catch `asyncio.TimeoutError`: log warning, return failed status dict with `"error_code": "agent_timeout"`, score=None
        - Log timing: `logger.info("[TIMING] %s agent: %d chars sent, completed in %.1fs", agent_display_name, len(chunk['text']), elapsed)`
      - Store truncation flags in a dict and pass to final result for frontend display
      
      **Gotchas:**
      - Sequential mode agents are sync functions run via `loop.run_in_executor()` in parallel mode, but called directly in sequential mode
      - Need to handle timeout for both sync (sequential) and async (parallel) execution paths
      - Agent timeout should NOT crash the pipeline — mark agent failed, continue with others
      
      **Files:** `backend/app/services/orchestrator.py`
      
      **Verify:** Set AGENT_TIMEOUT_SECONDS=5 in .env, run analysis on a test PDF — agents should timeout individually and pipeline should complete with partial results. Check backend logs for "[TIMING]" messages showing chars sent and time per agent.

- [ ] 4. **Modify llm_client.py to pass Ollama options from config**
      
      Changes to `backend/app/services/llm_client.py`:
      - Import `OLLAMA_NUM_CTX, OLLAMA_NUM_PREDICT, OLLAMA_TEMPERATURE, OLLAMA_KEEP_ALIVE` from config
      - In `call_llm()`, update the `payload["options"]` dict:
        ```python
        payload["options"] = {
            "temperature": OLLAMA_TEMPERATURE,
            "num_ctx": OLLAMA_NUM_CTX,
            "num_predict": OLLAMA_NUM_PREDICT,
        }
        ```
      - Add `"keep_alive": OLLAMA_KEEP_ALIVE` to payload root (not in options dict — Ollama API expects it at root level)
      - Remove hardcoded `"temperature": 0.1` — use config value
      - Keep existing `format_json` parameter handling (already sets `payload["format"] = "json"`)
      
      **Files:** `backend/app/services/llm_client.py`
      
      **Verify:** Add debug logging to print payload before POST, run analysis, check backend logs for correct num_ctx=4096, temperature=0.2, keep_alive=30m

- [ ] 5. **Add warm-up on backend startup in main.py**
      
      Changes to `backend/app/main.py`:
      - Import `call_llm` from llm_client, `OLLAMA_BASE_URL, LLM_MODEL` from config
      - Modify the existing `@app.on_event("startup")` function to include warm-up:
        ```python
        @app.on_event("startup")
        def on_startup():
            init_db()
            run_migrations()
            # Warm-up Ollama model
            try:
                logger.info("Warming up Ollama model %s...", LLM_MODEL)
                call_llm(
                    system_prompt="You are a helpful assistant.",
                    user_prompt="Say 'ready' in one word.",
                    timeout=30.0,
                )
                logger.info("Model warm-up complete.")
            except Exception as e:
                logger.warning("Model warm-up failed (non-fatal): %s", e)
        ```
      
      **Gotchas:**
      - Warm-up failure should NOT crash startup — catch all exceptions
      - Use short timeout (30s) for warm-up
      - Log at INFO level for success, WARNING for failure
      
      **Files:** `backend/app/main.py`
      
      **Verify:** Restart backend, check logs for "Warming up Ollama model" and "Model warm-up complete" messages. First analysis should be faster than before (no initial model loading delay).

- [ ] 6. **Add progress tracking endpoint and state management**
      
      Changes to `backend/app/services/orchestrator.py`:
      - Add module-level dict: `_progress_state: Dict[str, Dict[str, Any]] = {}` (evaluation_id → progress info)
      - Add helper functions:
        ```python
        def set_progress(eval_id: str, current_agent: str, completed: int, total: int):
            _progress_state[eval_id] = {
                "current_agent": current_agent,
                "completed": completed,
                "total": total,
                "timestamp": time.time()
            }
        
        def get_progress(eval_id: str) -> Optional[Dict[str, Any]]:
            return _progress_state.get(eval_id)
        
        def clear_progress(eval_id: str):
            _progress_state.pop(eval_id, None)
        ```
      - In `run_full_evaluation()`:
        - Accept optional `evaluation_id: Optional[str] = None` parameter
        - If provided, call `set_progress(evaluation_id, "general_analysis", 0, 6)` before each stage
        - Update progress after each agent completes: `set_progress(evaluation_id, "novelty", 2, 6)` etc.
        - Total is 6: general_analysis (1) + 4 agents + coordinator (1)
        - Call `clear_progress(evaluation_id)` at the end
      
      Changes to `backend/app/routes/evaluations.py`:
      - Import `get_progress` from orchestrator
      - Add new endpoint:
        ```python
        @router.get("/evaluations/{record_id}/progress")
        def get_evaluation_progress(record_id: str):
            progress = get_progress(record_id)
            if not progress:
                raise HTTPException(status_code=404, detail="No active analysis for this ID")
            return progress
        ```
      
      Changes to `backend/app/routes/analyze.py`:
      - Generate a temporary evaluation_id before calling orchestrator: `eval_id = str(uuid.uuid4())`
      - Pass it to `run_full_evaluation(..., evaluation_id=eval_id)`
      
      **Gotchas:**
      - Progress state is in-memory only — cleared on backend restart
      - evaluation_id for in-progress analyses won't match final saved DB id (that's OK — frontend can poll by temporary id during analysis)
      - Need to import uuid in analyze.py
      
      **Files:** `backend/app/services/orchestrator.py`, `backend/app/routes/evaluations.py`, `backend/app/routes/analyze.py`
      
      **Verify:** Start analysis, immediately call GET /api/evaluations/{temp_id}/progress — should return current_agent and completed count. Poll every 2s, verify it updates as agents complete.

- [ ] 7. **Update frontend NewAnalysis.jsx to show per-agent progress**
      
      Changes to `frontend/src/views/NewAnalysis.jsx`:
      - Add state: `const [progressInfo, setProgressInfo] = useState(null)` and `const [analysisId, setAnalysisId] = useState(null)`
      - In `handleAnalyze()`, after starting the POST /api/analyze:
        - Extract a temporary ID from response headers or generate one client-side (match backend approach)
        - Start polling: `const pollInterval = setInterval(() => fetchProgress(tempId), 2000)`
        - Stop polling when analysis completes or errors: `clearInterval(pollInterval)`
      - Add `fetchProgress()` function:
        ```javascript
        const fetchProgress = async (id) => {
          try {
            const res = await fetch(`${API_BASE_URL}/api/evaluations/${id}/progress`)
            if (res.ok) {
              const data = await res.json()
              setProgressInfo(data)
            }
          } catch (err) {
            // Ignore errors (analysis may have completed and cleared progress)
          }
        }
        ```
      - Update loading message to show progress:
        ```javascript
        {progressInfo && (
          <p>Analyzing... {progressInfo.current_agent} ({progressInfo.completed} of {progressInfo.total} done)</p>
        )}
        ```
      - Clear progressInfo on reset and when analysis completes
      
      **Gotchas:**
      - Backend clears progress when analysis completes, so 404 on progress endpoint is normal at the end
      - Stop polling on unmount to avoid memory leaks
      - Agent names from backend are lowercase (novelty_agent) — format for display (Novelty Agent)
      
      **Files:** `frontend/src/views/NewAnalysis.jsx`
      
      **Verify:** Upload PDF, watch status message update from "General Analysis (1/6)" → "Novelty (2/6)" → ... → "Coordinator (6/6)". Confirm polling stops when analysis completes.

- [ ] 8. **Enhance error handling and classification in llm_client.py**
      
      Changes to `backend/app/services/llm_client.py`:
      - Add `error_code` field to `LLMClientError` class:
        ```python
        class LLMClientError(Exception):
            def __init__(self, message: str, status_code: int = 500, error_code: str = "llm_error"):
                super().__init__(message)
                self.message = message
                self.status_code = status_code
                self.error_code = error_code
        ```
      - Update exception raising to set error_code:
        - Connection errors: `error_code="ollama_not_running"`
        - Model not found: `error_code="model_not_found"`
        - Timeout: `error_code="llm_timeout"`
        - Other errors: `error_code="llm_error"`
      
      Changes to `backend/app/routes/analyze.py`:
      - Catch `LLMClientError` and return error_code in response:
        ```python
        except LLMClientError as llm_err:
            raise HTTPException(
                status_code=llm_err.status_code,
                detail={"message": llm_err.message, "error_code": llm_err.error_code}
            )
        ```
      
      Changes to `frontend/src/views/NewAnalysis.jsx`:
      - Update error handling to check `data?.error_code`:
        ```javascript
        const errorCode = data?.error_code || (typeof data?.detail === 'object' ? data.detail.error_code : null)
        const errorMsg = typeof data?.detail === 'string' ? data.detail : data?.detail?.message || `Server error ${res.status}`
        
        if (errorCode === 'ollama_not_running' || errorCode === 'model_not_found') {
          setIsOllamaError(true)
        } else if (errorCode === 'agent_timeout') {
          setAnalyzeError('The model is slow on this machine. Try a shorter document or the sample demos.')
          setIsOllamaError(false) // Don't show Ollama checklist for timeouts
        } else {
          setAnalyzeError(errorMsg)
          setIsOllamaError(isOllamaMsg(errorMsg))
        }
        ```
      
      **Files:** `backend/app/services/llm_client.py`, `backend/app/routes/analyze.py`, `frontend/src/views/NewAnalysis.jsx`
      
      **Verify:** Test each error case:
      - Stop Ollama → upload PDF → should show "Start Ollama" checklist
      - Wrong model name → should show "Run: ollama pull ..." message
      - Set AGENT_TIMEOUT_SECONDS=1 → upload PDF → should show "The model is slow..." message WITHOUT Ollama checklist

- [ ] 9. **Add enhanced logging throughout the pipeline**
      
      Changes to `backend/app/services/orchestrator.py`:
      - At start of `run_full_evaluation()`: log total pipeline start time
      - After each agent: log `[TIMING] {agent_name}: {chars_sent} chars sent, completed in {elapsed:.1f}s`
      - After coordinator: log coordinator timing
      - At end of pipeline: log total time and agent success/failure counts
        ```python
        logger.info("[PIPELINE] Total time: %.1fs | Success: %d/6 | Failed: %d/6",
                   total_time, success_count, fail_count)
        ```
      
      Changes to `backend/app/services/text_chunker.py`:
      - Log for each agent: `[text_chunker] {agent_name}: {chars} chars selected via {method} (truncated={bool})`
      
      **Files:** `backend/app/services/orchestrator.py`, `backend/app/services/text_chunker.py`
      
      **Verify:** Run analysis, check backend console for structured timing logs:
      ```
      [TIMING] novelty: 5234 chars sent, completed in 127.3s
      [TIMING] technical: 4821 chars sent, completed in 98.6s
      ...
      [PIPELINE] Total time: 423.7s | Success: 6/6 | Failed: 0/6
      ```

- [ ] 10. **Update frontend to show truncation notices**
      
      Changes to `frontend/src/views/NewAnalysis.jsx`:
      - Check if `analysisResult` includes truncation flags (add to orchestrator result if text was chunked)
      - Display notice banner below the analysis results if any agent had truncated input:
        ```jsx
        {analysisResult?.truncation_applied && (
          <div className="alert-banner" role="alert" style={{background: '#fef3c7', border: '1px solid #f59e0b'}}>
            <p>⚠️ Input text was shortened for some agents to improve performance. Results are based on relevant sections only.</p>
          </div>
        )}
        ```
      
      **Gotchas:**
      - Orchestrator needs to collect truncation flags from all agents and add to result as `truncation_applied: bool`
      - Demo results won't have this flag (they were pre-computed) — that's OK
      
      **Files:** `backend/app/services/orchestrator.py` (to add flag), `frontend/src/views/NewAnalysis.jsx`
      
      **Verify:** Upload a long PDF (>6000 chars), confirm truncation notice appears. Upload a short PDF, confirm no notice.

- [ ] 11. **Test with real proposals and verify all requirements**
      
      Test cases:
      1. **Short PDF (< 1 page)**: Should complete quickly (~60-120s), no truncation notice
      2. **Long PDF (10+ pages)**: Should show truncation notice, complete in ~7-9 minutes
      3. **Forced timeout**: Set AGENT_TIMEOUT_SECONDS=5, verify individual agents timeout but pipeline completes with partial results
      4. **Connection error**: Stop Ollama, verify "Start Ollama" checklist appears (not generic error)
      5. **Model not found**: Change LLM_MODEL to nonexistent model, verify "ollama pull" message
      6. **Progress tracking**: Upload PDF, watch progress indicator update through 6 stages
      7. **Demo mode**: Verify cached demos still load instantly
      
      **Verify:**
      - Backend logs show `[TIMING]` entries with chars sent and time per agent
      - Backend logs show `[PIPELINE]` summary with total time and success/fail counts
      - Frontend shows per-agent progress during analysis
      - Error messages distinguish Ollama offline, model missing, and timeout cases
      - Truncation notice appears for long documents
      - Demo mode unchanged (still loads cached results instantly)
      - Sequential execution confirmed (AGENT_CONCURRENCY=1, PARALLEL_AGENTS=false in .env)

---

## New .env variables summary

```bash
# Agent execution control
AGENT_CONCURRENCY=1                  # Max concurrent agents (1=sequential, 2+=parallel if PARALLEL_AGENTS=true)
AGENT_TIMEOUT_SECONDS=180            # Per-agent timeout in seconds
MAX_CHARS_PER_AGENT=6000             # Max chars to send per agent (keyword-based selection)

# Ollama performance tuning
OLLAMA_NUM_CTX=4096                  # Context window size
OLLAMA_NUM_PREDICT=500               # Max output tokens
OLLAMA_TEMPERATURE=0.2               # Temperature (lower=more deterministic)
OLLAMA_KEEP_ALIVE=30m                # Keep model loaded in memory
OLLAMA_FORMAT=json                   # Not used directly (format_json param controls this)
```

## Files to modify

1. `backend/.env` — add new config variables
2. `backend/app/config/__init__.py` — load new config variables
3. `backend/app/services/text_chunker.py` — NEW FILE, keyword-based text extraction
4. `backend/app/services/orchestrator.py` — AGENT_CONCURRENCY, per-agent timeouts, text chunking, progress tracking, enhanced logging
5. `backend/app/services/llm_client.py` — Ollama options from config, error_code field
6. `backend/app/main.py` — warm-up on startup
7. `backend/app/routes/evaluations.py` — GET /api/evaluations/{id}/progress endpoint
8. `backend/app/routes/analyze.py` — generate temp eval_id, pass to orchestrator, return error_code
9. `frontend/src/views/NewAnalysis.jsx` — progress polling, per-agent status display, error code handling, truncation notice

## Test commands

```bash
# Backend
cd backend
python -c "from app.config import AGENT_TIMEOUT_SECONDS, MAX_CHARS_PER_AGENT; print(AGENT_TIMEOUT_SECONDS, MAX_CHARS_PER_AGENT)"

# Start backend and verify warm-up
uvicorn app.main:app --reload --port 8000
# Check logs for "Warming up Ollama model" and "Model warm-up complete"

# Test analysis with timing logs
# Upload a PDF via frontend, watch backend console for [TIMING] and [PIPELINE] logs

# Frontend
cd frontend
npm run dev
# Navigate to http://localhost:5173, upload PDF, verify progress indicator updates
```

## Gotchas discovered

1. **Parallel mode complexity**: Current parallel implementation uses asyncio.Semaphore but agents are sync functions wrapped in executor. Timeout handling requires wrapping the executor call with asyncio.wait_for().

2. **Sequential vs parallel paths**: Sequential mode currently calls agents directly (sync), parallel mode wraps in executor. Both need timeout handling but use different mechanisms.

3. **Progress tracking IDs**: Temporary evaluation_id for progress tracking won't match final saved DB id. Frontend polls by temp ID during analysis, then switches to saved ID after completion.

4. **Text chunking per agent**: Each agent needs different keywords. Novelty agent already does paper search, so it still needs broader context. Financial agent needs budget tables which might be in specific sections.

5. **Ollama options location**: `keep_alive` goes at payload root level, not in `options` dict. `format` is set via `format_json` parameter, not from config.

6. **Error code structure**: HTTPException detail can be string or dict. Frontend needs to handle both formats.

7. **Agent timeout vs LLM timeout**: LLM client has REQUEST_TIMEOUT_SECONDS (global), orchestrator now has AGENT_TIMEOUT_SECONDS (per-agent, includes all LLM calls + processing for that agent). Agent timeout should be >= LLM timeout.

8. **Demo mode preservation**: Cached demo results are pre-computed full results. They won't have truncation flags or new error structures. Frontend should handle missing fields gracefully.

9. **Warm-up timing**: Warm-up on startup means first real analysis is faster, but adds ~5-10s to backend startup time. Non-fatal failure is correct approach.

10. **Logging format**: Use `[TIMING]`, `[PIPELINE]`, `[text_chunker]` prefixes for easy log filtering and monitoring.
