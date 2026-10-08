# AI-Based Multi-Agent R&D Proposal Evaluation System

An AI-assisted tool that helps a human reviewer evaluate R&D / research proposals. A reviewer uploads a proposal PDF, four specialized AI agents analyze it in parallel, and a Coordinator agent combines their findings into a scored, evidence-backed evaluation report.

> **AI-generated preliminary evaluation.** This system assists reviewers, it does not replace them. Final decisions stay with a human.

---

## Table of Contents

1. [The Problem](#the-problem)
2. [Key Features](#key-features)
3. [How It Works](#how-it-works)
4. [Tech Stack](#tech-stack)
5. [Project Structure](#project-structure)
6. [Prerequisites](#prerequisites)
7. [Setup and Run](#setup-and-run)
8. [Configuration](#configuration)
9. [Using the App](#using-the-app)
10. [Demo Mode (Cached Results)](#demo-mode-cached-results)
11. [Testing](#testing)
12. [Performance Notes](#performance-notes)
13. [Limitations](#limitations)
14. [Privacy](#privacy)
15. [Roadmap](#roadmap)

---

## The Problem

Reviewing R&D proposals is slow and inconsistent. Each proposal needs separate checks for novelty, technical feasibility, budget accuracy and expected impact, and the quality of review varies from reviewer to reviewer. Budget arithmetic errors and overlap with existing work are easy to miss.

## Key Features

- **PDF upload and page-wise text extraction** (PyMuPDF), processed fully in memory. Uploads are never saved to disk.
- **Four specialized agents running in parallel:**
  - **Novelty Agent:** identifies the claimed innovation, similarity concerns and missing evidence, using an external scholarly paper search for real evidence.
  - **Technical Feasibility Agent:** examines methodology, data needs, hardware/software, challenges and implementation risks.
  - **Financial Agent:** the LLM only *extracts* budget items. **Python does all the arithmetic**, comparing sums against stated totals and flagging mismatches and missing costs.
  - **Impact Agent:** looks at beneficiaries, problem significance, expected benefits and measurable outcomes.
- **Coordinator Agent:** produces a weighted overall score, a recommendation (for example "Revise and Resubmit") and reasoning. It clearly separates agents that were *scored*, *not applicable* (for example no budget section found) and *failed*.
- **Evidence-grounded output:** findings cite the proposal, and missing information is reported as "Not stated in proposal" rather than guessed.
- **Prompt-injection protection:** the proposal text is treated strictly as untrusted data, never as instructions.
- **Graceful failure handling:** if one agent fails or times out, the others still return.
- **Reviewer override:** a human can adjust or override the final recommendation.
- **History and Archive:** every evaluation is saved to a local SQLite database.
- **Portfolio Analytics:** view trends across all evaluated proposals.
- **Runs locally:** uses a local LLM through Ollama, so no paid API is needed.
- **Demo mode:** "Try a sample proposal" dropdown with pre-computed cached results for fast, reliable demos.

## How It Works

```
          Reviewer uploads proposal PDF
                      |
                      v
        React + Vite frontend (port 5173)
                      |
                      v
           FastAPI backend (port 8000)
      PDF validation + PyMuPDF text extraction
              + text chunker (per agent)
                      |
                      v
              Agent Orchestrator
        (runs 4 agents in parallel, each
              with its own timeout)
        /          |           |         \
       v           v           v          v
   Novelty    Technical    Financial    Impact
    Agent       Agent        Agent       Agent
  (+ paper                 (+ Python
   search)                  budget math)
        \          |           |         /
         v         v           v        v
                Coordinator Agent
        (weighted score + recommendation
                  + reasoning)
                      |
                      v
        Report shown to reviewer + saved
          to SQLite (History / Analytics)

   Shared services: Ollama (local LLM) | Paper search API | SQLite
```

**Agent output format.** Every agent returns the same JSON schema so the Coordinator can combine them: `agent_name`, `status`, `summary`, `findings` (with `evidence` and `severity`), `missing_information`, `questions_for_reviewer`, `confidence` and `error` (if failed).

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React + Vite, plain CSS |
| Backend | Python, FastAPI, Uvicorn |
| PDF processing | PyMuPDF (fitz) |
| LLM | Ollama running `gemma3:4b` (local, CPU-friendly) |
| Novelty evidence | External scholarly paper search |
| Database | SQLite (`evaluations.db`) |

## Project Structure

> Adjust file names below if your repo differs slightly.

```
R&D_analyzer/
├── README.md
├── .gitignore
├── backend/
│   ├── requirements.txt
│   ├── .env.example              # Copy to .env and edit
│   ├── scripts/
│   │   └── export_demo.py        # Dev script: export a saved evaluation as a cached demo
│   └── app/
│       ├── main.py               # FastAPI entry point, CORS, router mounting
│       ├── routes/               # API endpoints (health, upload, analyze, history, ...)
│       ├── agents/               # base_agent, novelty, technical, financial, impact, coordinator
│       ├── services/
│       │   ├── pdf_service.py        # In-memory PDF validation + extraction
│       │   ├── llm_client.py         # Reusable call to the local Ollama model
│       │   ├── text_chunker.py       # Selects relevant text per agent
│       │   ├── orchestrator.py       # Runs agents in parallel with timeouts
│       │   ├── budget_calculator.py  # Decimal-based budget math (Financial Agent)
│       │   └── paper_search.py       # External paper search for Novelty Agent
│       └── data/
│           └── cached_demo_results/  # Pre-computed demo evaluations (JSON)
└── frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── App.jsx
        ├── App.css
        ├── config.js             # API base URL (http://localhost:8000)
        └── main.jsx
```

## Prerequisites

- **Python** 3.10+
- **Node.js** 18+ (with npm)
- **Ollama**, installed from https://ollama.com
- A laptop with roughly 8 GB RAM or more (a GPU is optional but speeds things up a lot)

## Setup and Run

You will use three terminals: Ollama, backend and frontend.

### 1. Local LLM (Ollama)

```bash
ollama pull gemma3:4b
ollama serve        # skip if Ollama is already running in the background
```

### 2. Backend (FastAPI, port 8000)

**Windows (PowerShell):**
```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
# If scripts are blocked: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

**macOS / Linux:**
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

- API: http://localhost:8000
- Health check: http://localhost:8000/api/health
- Swagger docs: http://localhost:8000/docs

### 3. Frontend (React + Vite, port 5173)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The status bar should show the backend and the LLM as connected.

## Configuration

Settings live in `backend/.env` (copy from `.env.example`). **Never commit `.env`.**

| Variable | Purpose | Suggested default |
|---|---|---|
| `LLM_MODEL` | Ollama model name | `gemma3:4b` |
| `LLM_TIMEOUT_SECONDS` | Per-call LLM timeout | `900` |
| `AGENT_TIMEOUT_SECONDS` | Timeout per agent | see `.env.example` |
| `NOVELTY_TIMEOUT_SECONDS` | Timeout for the Novelty LLM call only | `240` |
| `MAX_CHARS_PER_AGENT` | Max text characters sent to each agent | `3000`–`4500` |
| `OLLAMA_NUM_PREDICT` | Max output tokens per agent | `400` |
| `COORDINATOR_NUM_PREDICT` | Max output tokens for the Coordinator | `900` |

The Ollama context size (`num_ctx`) is set to `4096`. See `.env.example` for the exact variable names in your version.

## Using the App

1. Open the **New Analysis** page.
2. Upload a proposal PDF (drag and drop, or browse), or choose **Try a sample proposal**.
3. Click **Upload & Analyze**.
4. Wait for the four agents and the Coordinator to finish.
5. Review the overall score, the recommendation, the per-agent cards (findings, evidence, missing information, questions) and the Coordinator's reasoning.
6. Optionally apply a **reviewer override**.
7. Open **History & Archive** to revisit saved evaluations, and **Portfolio Analytics** to see trends across proposals.

## Demo Mode (Cached Results)

Running a full analysis on a CPU laptop can take several minutes. For fast, reliable demos, the app includes sample proposals with **pre-computed results** stored in `backend/app/data/cached_demo_results/`.

- Pick a proposal from **Try a sample proposal** to load its cached result instantly.
- To add your own cached demo from a real run:
```bash
  cd backend
  python scripts/export_demo.py <evaluation_id> <demo_name>
```
  (Check the script's `--help` for the exact arguments.)

## Testing

**PDF extraction tests** (valid PDF, empty file, oversize, non-PDF, missing header, password-protected, corrupted, scanned/no text):
```bash
cd backend
python test_brick2.py
```

**Budget calculator tests** (sums, stated-total mismatches, percentages):
run the unit tests for `budget_calculator.py` (see the `tests` folder or the test file in `backend`).

**Manual checks in the UI:**

| Test | Expected result |
|---|---|
| Valid proposal PDF | Full evaluation with four agent cards and a Coordinator report |
| Scanned / image-only PDF | Clear error: no extractable text, OCR not supported |
| Password-protected PDF | Clear error asking for an unprotected file |
| Non-PDF file | Clear validation error |
| Proposal with a wrong budget total | Financial Agent flags the mismatch |
| Proposal with no budget section | Financial shown as "Not applicable", not as a failure |
| Ollama stopped | Friendly error, not a crash |

## Performance Notes

- The local model runs on CPU by default, so a long real report can take **10–20 minutes** and a tiny test file around **7 minutes**. Most of the time is fixed generation cost per agent call.
- To speed things up: plug in the charger, close heavy apps, lower `MAX_CHARS_PER_AGENT` and the `*_NUM_PREDICT` values, or use a machine with a GPU.
- For quick tests only, a smaller model such as `gemma3:1b` is faster but lower quality.

## Limitations

- **No OCR.** Scanned or image-only PDFs are rejected with a clear message.
- **Novelty is evidence-limited.** The Novelty Agent never claims an idea is fully original. It relies on external paper search results, so its confidence is kept conservative.
- **Small local model.** `gemma3:4b` is fast enough for a prototype but less capable than large hosted models.
- **File size limit:** 10 MB per PDF.
- **Preliminary only.** Output is an AI-generated aid and must be verified by a human reviewer.

## Privacy

Proposals may be confidential. Analysis uses a **local LLM**, uploaded PDFs are processed **in memory** and not stored, and results are saved only to the local SQLite database on your machine. Note that the Novelty Agent's paper search sends search queries to an external service.

## Roadmap

- PDF export of the final report
- OCR support for scanned proposals
- GPU or hosted-model option for much faster runs
- User accounts and multi-reviewer workflows
- Richer novelty search across more scholarly sources
