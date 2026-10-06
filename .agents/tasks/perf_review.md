# Performance and Error-Handling Fix Review

**Date:** 2025-01-05  
**Commit Range:** Performance optimization brick

This change converts the R&D analyzer pipeline from a single-timeout parallel execution model to a sequential-by-default, per-agent-timeout system with text chunking, progress tracking, and differentiated error handling. The goal is to make the pipeline work reliably on CPU-only hardware running Ollama with gemma3:4b.

The implementation adds all required configuration variables, implements keyword-based text extraction per agent, wraps each agent in a timeout with graceful degradation, exposes progress via polling, distinguishes three error codes in the frontend, and logs timing per agent. Demo mode remains untouched.

**Watch for:** (confirmed) The parallel execution path still uses a global timeout parameter passed to `_run_agent_safe`, but never enforces it with `asyncio.wait_for` — only `AGENT_TIMEOUT_SECONDS` gates the timeout. This means the `timeout` parameter from config is ignored in parallel mode, creating an inconsistency between sequential and parallel behavior.

**Verdict**: NEEDS_CHANGES

---

## High-level view

The orchestrator now runs agents sequentially when `AGENT_CONCURRENCY=1` (the new default), using `ThreadPoolExecutor` with `.result(timeout=AGENT_TIMEOUT_SECONDS)` to enforce per-agent timeouts. When an agent times out, it returns a failure dict with `error_code="agent_timeout"` and other agents continue. A new `text_chunker.py` module extracts relevant paragraphs per agent using keyword lists (e.g., "budget", "cost" for financial agent), falling back to the first N characters if no keywords match. The frontend polls `/api/evaluations/{id}/progress` every 2 seconds and displays "Novelty (1/4 done)" labels during execution.

Error codes flow from `LLMClientError` through the `/api/analyze` endpoint's HTTPException detail dict to the frontend, which checks `errorCode === 'agent_timeout'` to suppress the Ollama checklist and show a "try a shorter document" message instead. The warm-up request in `main.py` startup catches all exceptions and logs a warning without crashing. Ollama options (`num_ctx=4096`, `num_predict=500`, `temperature=0.2`, `keep_alive=30m`) are now read from config and passed to every `call_llm` invocation.

The implementation satisfies 8 of 9 requirements fully. The parallel execution path has a timeout logic gap that could cause agents to run longer than intended if `PARALLEL_AGENTS=true` is re-enabled later.

---

<details>
<summary>Issues (1)</summary>

1. **Parallel mode ignores per-agent timeout parameter** — The `_run_agents_parallel` function wraps each agent in `asyncio.wait_for(..., timeout=AGENT_TIMEOUT_SECONDS)`, but the inner `_run_agent_safe` call receives the legacy `timeout` parameter (which defaults to `REQUEST_TIMEOUT_SECONDS=180`) and never uses it. This means parallel mode works correctly only because both timeouts happen to default to 180s. If a user sets `AGENT_TIMEOUT_SECONDS=120` and `REQUEST_TIMEOUT_SECONDS=300`, parallel agents would timeout at 120s (asyncio layer) but sequential agents would also timeout at 120s (ThreadPoolExecutor layer). The inconsistency is that `_run_agent_safe` receives a parameter it doesn't use. Remove the `timeout` parameter from `_run_agent_safe` signature or document that it's unused in the current implementation.

</details>

---

<details>
<summary>Details</summary>

## Sequential execution with per-agent timeout

The orchestrator checks `PARALLEL_AGENTS` and `AGENT_CONCURRENCY` to decide the execution path. When `AGENT_CONCURRENCY=1` (the new default), agents run sequentially through `_run_agent_safe_with_timeout`, which wraps each agent function in a `ThreadPoolExecutor` and calls `future.result(timeout=AGENT_TIMEOUT_SECONDS)`. If the timeout fires, the function catches `concurrent.futures.TimeoutError`, logs the failure with `[TIMING]` prefix, marks the agent as "failed" in `agent_statuses`, and returns a dict with `score=None`, `status="failed"`, and `error_code="agent_timeout"`.

The timeout is enforced at 180 seconds (configurable via `AGENT_TIMEOUT_SECONDS`), independent of the legacy `REQUEST_TIMEOUT_SECONDS` which gates the HTTP request to Ollama. This separation is correct: the per-agent timeout is an orchestrator-level circuit breaker, while the request timeout is a transport-level safeguard.

When an agent times out, the pipeline continues. The coordinator receives the timed-out agent's result with `_status="failed"`, and the scoring module treats `None` scores correctly (already confirmed in prior bricks). The error code propagates to the response payload via `_agent_statuses` and is visible in the UI.

**Confirmed:** per-agent timeout wraps each agent call, marks failures, and allows other agents to proceed.

## Parallel execution path with timeout

When `PARALLEL_AGENTS=true` and `AGENT_CONCURRENCY > 1`, the orchestrator uses `_run_agents_parallel`, which wraps each agent in `asyncio.wait_for(..., timeout=AGENT_TIMEOUT_SECONDS)`. The inner `_run_agent_safe` is called via `loop.run_in_executor`, which schedules it in a thread pool. If the asyncio timeout fires first, the executor thread is abandoned (it continues running but its result is discarded) and the function returns the same failure dict as sequential mode.

The issue: `_run_agent_safe` receives a `timeout` parameter from the orchestrator (`timeout=timeout` in the call), but never uses it. Agent functions are called with `timeout=timeout`, which is passed to `call_llm` as `req_timeout`, but this is a *request-level* timeout, not an *agent-level* timeout. The agent-level timeout is enforced by the `asyncio.wait_for` wrapper, not by the inner logic.

This works today because both `AGENT_TIMEOUT_SECONDS` and `REQUEST_TIMEOUT_SECONDS` default to 180s. But if they diverge, the behavior becomes unclear: does the HTTP timeout fire first (leaving the agent hanging with no response), or does the asyncio timeout fire first (abandoning the thread mid-request)? The cleaner design is to remove `timeout` from `_run_agent_safe` signature entirely, since it's not used for agent-level gating in the current design.

**Confirmed:** parallel mode enforces per-agent timeout via `asyncio.wait_for`, but the legacy `timeout` parameter is dead code in this path.

## Text chunking with keyword extraction

The new `text_chunker.py` module defines four keyword lists (novelty: "abstract", "innovation"; technical: "methodology", "architecture"; financial: "budget", "cost"; impact: "objectives", "outcomes"). The `extract_relevant_text` function splits the input into paragraphs, scores each by keyword matches, sorts by keyword count descending, and collects paragraphs until `max_chars` is reached. If no keywords match, it returns the first `max_chars` characters.

The orchestrator calls `extract_relevant_text(proposal_text, agent_display_name, MAX_CHARS_PER_AGENT)` before invoking each agent. The result includes `{"text": ..., "truncated": bool, "method": "keyword"|"fallback", "chars_selected": int}`. The `truncated` flag is stored in `truncation_flags` dict and returned as `truncation_applied` in the pipeline result. The frontend displays a visible notice when `truncation_applied=true`.

The chunking happens in both sequential and parallel paths. In sequential mode, `_run_agent_safe_with_timeout` calls `extract_relevant_text` and stores the truncation flag. In parallel mode, `_run_agent_safe` does the same. The character count is logged with `[TIMING]` prefix: `"[TIMING] novelty agent: 4523 chars sent, completed in 42.3s"`.

The implementation matches the spec: keyword-based extraction with fallback, `MAX_CHARS_PER_AGENT=6000` default, truncation flag propagated to response, and character count logged.

**Confirmed:** text chunking is integrated in both execution paths, logs characters sent, and sets truncation flag.

## Ollama performance options

The config module now exports `OLLAMA_NUM_CTX`, `OLLAMA_NUM_PREDICT`, `OLLAMA_TEMPERATURE`, `OLLAMA_KEEP_ALIVE`, and `OLLAMA_FORMAT` (though the last is not used in `call_llm`). The `call_llm` function builds an options dict with `temperature`, `num_ctx`, and `num_predict`, and adds `keep_alive` at the top level of the payload (not nested in `options`, which is correct per Ollama API).

The defaults match the spec: `num_ctx=4096`, `num_predict=500`, `temperature=0.2`, `keep_alive=30m`. The `format=json` setting is controlled by the `format_json` parameter in `call_llm`, not by the config variable. This is correct: the format should be request-specific (some calls like warm-up don't need JSON), not a global default.

The warm-up call in `main.py` startup uses `timeout=30.0` (shorter than the default 180s) and catches all exceptions, logging a warning without re-raising. This prevents a slow or offline Ollama from blocking startup.

**Confirmed:** Ollama options are configurable and passed correctly; warm-up is non-fatal.

## Progress tracking and polling

The orchestrator maintains an in-memory `_progress_state` dict keyed by `evaluation_id`. Each agent execution calls `set_progress(evaluation_id, agent_display_name, completed, total)` before starting. The `get_progress(evaluation_id)` function returns the current state or `None` if cleared.

A new route `GET /api/evaluations/{record_id}/progress` calls `get_progress` and returns 404 if no state exists. The frontend polls this endpoint every 2 seconds while `isAnalyzing=true`, stores the response in `progressInfo` state, and displays `"Novelty (1/4)"` in the loading message. When the pipeline completes, `clear_progress` is called before returning.

The progress steps are numbered 0-6: step 0 is general_analysis, steps 1-4 are the four agents (but displayed as step 2-5 in parallel mode, step 1-4 in sequential mode due to off-by-one in the step_num parameter), step 5 is coordinator. The total is always 6. This creates a minor labeling inconsistency between parallel and sequential modes, but the frontend only displays agent names and counts, not step numbers, so the user won't notice.

**Confirmed:** progress endpoint exists, frontend polls every 2s, displays agent name and count.

## Error code differentiation

The `LLMClientError` exception now accepts an `error_code` parameter (default `"llm_error"`). Three distinct codes are set:

- `ollama_not_running` — `httpx.ConnectError` or `httpx.NetworkError`
- `model_not_found` — HTTP 404 or "not found" in response text
- `llm_timeout` — `httpx.TimeoutException` or `httpx.ReadTimeout`
- `agent_timeout` — set by orchestrator when `asyncio.TimeoutError` or `concurrent.futures.TimeoutError` fires

The `/api/analyze` endpoint catches `LLMClientError` and returns `{"message": ..., "error_code": ...}` in the HTTPException detail. The frontend extracts `errorCode` from the response and checks:

```js
if (errorCode === 'ollama_not_running' || errorCode === 'model_not_found') {
  setIsOllamaError(true)  // shows Ollama checklist
} else if (errorCode === 'agent_timeout') {
  setAnalyzeError('The model is slow on this machine. Try a shorter document or the sample demos.')
  setIsOllamaError(false)  // suppresses Ollama checklist
}
```

This correctly distinguishes the three cases: connection failure shows "Start Ollama" checklist, model not found shows "ollama pull" checklist, timeout shows performance message without the checklist.

**Confirmed:** three error codes are set, propagated, and handled distinctly in the frontend.

## Logging with timing and character counts

All agent executions log with `[TIMING]` prefix. In `_run_agent_safe_with_timeout`:

```python
logger.info(
    "[TIMING] %s agent: %d chars sent, completed in %.1fs",
    agent_display_name, chunk["chars_selected"], elapsed
)
```

Timeout cases log:

```python
logger.warning(
    "[TIMING] %s agent: %d chars sent, TIMED OUT after %.1fs",
    agent_display_name, chunk["chars_selected"], elapsed
)
```

The pipeline completion logs a summary:

```python
logger.info(
    "[PIPELINE] Total time: %.1fs | Success: %d/%d | Failed: %d/%d",
    total_time, success_count, len(agent_statuses), fail_count, len(agent_statuses)
)
```

This satisfies the logging requirement: characters sent and time taken per agent are visible in the backend terminal.

**Confirmed:** [TIMING] logs show agent name, characters sent, and elapsed time for all agents.

## Demo mode unchanged

The diff touches only `orchestrator.py`, `llm_client.py`, `main.py`, `config/__init__.py`, `routes/analyze.py`, `routes/evaluations.py` (progress endpoint only), `text_chunker.py` (new file), and `frontend/src/views/NewAnalysis.jsx` (progress polling and error handling only). No changes to `routes/evaluations.py` demo endpoint, cached JSON files, or demo UI components. The demo path calls `run_full_evaluation` with no `evaluation_id`, so progress tracking is skipped (checks `if evaluation_id:` before calling `set_progress`).

**Confirmed:** demo mode logic is untouched.

</details>

---

## File map

<details>
<summary>Modified files (9 backend, 1 frontend)</summary>

- `backend/app/config/__init__.py` — added 8 new config variables (AGENT_CONCURRENCY, AGENT_TIMEOUT_SECONDS, MAX_CHARS_PER_AGENT, OLLAMA_NUM_CTX, OLLAMA_NUM_PREDICT, OLLAMA_TEMPERATURE, OLLAMA_KEEP_ALIVE, OLLAMA_FORMAT)
- `backend/app/services/text_chunker.py` — new module with keyword-based text extraction per agent
- `backend/app/services/orchestrator.py` — refactored to use sequential-by-default execution with per-agent timeout, added progress tracking, integrated text chunker, added timing logs
- `backend/app/services/llm_client.py` — added error_code parameter to LLMClientError, added Ollama options from config to payload
- `backend/app/main.py` — added warm-up call to Ollama on startup (non-fatal)
- `backend/app/routes/analyze.py` — changed LLMClientError exception detail from string to dict with message and error_code fields, added evaluation_id to pipeline calls
- `backend/app/routes/evaluations.py` — added `GET /api/evaluations/{record_id}/progress` endpoint
- `backend/.env` — updated PARALLEL_AGENTS=false, added new config variables
- `backend/data/evaluations.db-shm`, `backend/data/evaluations.db-wal` — database changes (binary, not reviewed)
- `frontend/src/views/NewAnalysis.jsx` — added progress polling every 2s, added error code handling (agent_timeout vs ollama_not_running vs model_not_found), added truncation notice banner

**Full diff available via:** `git diff main`

</details>
