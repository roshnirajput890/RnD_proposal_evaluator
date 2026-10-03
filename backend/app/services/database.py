"""
database.py — SQLite persistence layer for evaluated proposals.

Uses the Python standard-library sqlite3 only — no new dependencies.

DB file location: backend/data/evaluations.db
The data/ directory is created automatically on first use.

Schema (evaluations table):
    id              TEXT PRIMARY KEY   — auto-generated UUID
    filename        TEXT NOT NULL      — original PDF filename
    title_or_topic  TEXT               — LLM-extracted title
    main_idea       TEXT               — LLM main idea summary
    main_problem    TEXT               — LLM main problem
    proposed_solution TEXT             — LLM proposed solution
    page_count      INTEGER
    char_count      INTEGER
    model_used      TEXT               — Ollama model name at time of analysis
    status          TEXT DEFAULT 'completed'
    truncated       INTEGER DEFAULT 0  — 1 if input was truncated
    result_json     TEXT               — full JSON blob of the /api/analyze response
    created_at      TEXT               — ISO-8601 UTC timestamp
"""
import sqlite3
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── DB file path ───────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent.parent   # backend/
DATA_DIR = BASE_DIR / "data"
DB_PATH  = DATA_DIR / "evaluations.db"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS evaluations (
    id                TEXT PRIMARY KEY,
    filename          TEXT NOT NULL,
    title_or_topic    TEXT,
    main_idea         TEXT,
    main_problem      TEXT,
    proposed_solution TEXT,
    page_count        INTEGER,
    char_count        INTEGER,
    model_used        TEXT,
    status            TEXT DEFAULT 'completed',
    truncated         INTEGER DEFAULT 0,
    result_json       TEXT,
    created_at        TEXT NOT NULL
);
"""

_CREATE_IDX = """
CREATE INDEX IF NOT EXISTS idx_evaluations_created_at
    ON evaluations (created_at DESC);
"""


# ── Lifecycle ──────────────────────────────────────────────────────────────────

def init_db() -> None:
    """
    Create the data/ directory and evaluations table if they don't exist.
    Safe to call multiple times (CREATE IF NOT EXISTS).
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute(_CREATE_TABLE)
        conn.execute(_CREATE_IDX)
        conn.commit()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row          # access columns by name
    conn.execute("PRAGMA journal_mode=WAL") # concurrent read-write safety
    return conn


# ── Write ──────────────────────────────────────────────────────────────────────

def save_evaluation(
    *,
    filename:          str,
    analysis:          Dict[str, Any],   # the analysis sub-dict from /api/analyze
    page_count:        int,
    char_count:        int,
    model_used:        str,
    full_result:       Dict[str, Any],   # complete /api/analyze response
    # ── Coordinator fields (optional — absent on older saves) ──────────────
    coordinator_summary:         Optional[Dict[str, Any]] = None,
    preliminary_recommendation:  Optional[str] = None,
    recommendation_reasoning:    Optional[str] = None,
) -> str:
    """
    Insert one evaluation record and return its generated UUID.

    full_result is stored as a JSON blob so the complete response can be
    retrieved later without re-running the model.
    Coordinator fields are stored as JSON (coordinator_summary) or plain text.
    """
    record_id  = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    truncated  = 1 if analysis.get("truncated") else 0

    coord_json = (
        json.dumps(coordinator_summary, ensure_ascii=False)
        if coordinator_summary else None
    )

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO evaluations
                (id, filename, title_or_topic, main_idea, main_problem,
                 proposed_solution, page_count, char_count, model_used,
                 status, truncated, result_json, created_at,
                 coordinator_summary, preliminary_recommendation,
                 recommendation_reasoning)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                filename,
                analysis.get("title_or_topic", ""),
                analysis.get("main_idea_summary", ""),
                analysis.get("main_problem", ""),
                analysis.get("proposed_solution", ""),
                page_count,
                char_count,
                model_used,
                truncated,
                json.dumps(full_result, ensure_ascii=False),
                created_at,
                coord_json,
                preliminary_recommendation,
                recommendation_reasoning,
            ),
        )
        conn.commit()

    return record_id


# ── Read ───────────────────────────────────────────────────────────────────────

def get_evaluations(limit: int = 200) -> List[Dict[str, Any]]:
    """
    Return up to `limit` evaluation records, newest first.
    result_json is parsed back to a dict.
    """
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, filename, title_or_topic, main_idea, main_problem,
                   proposed_solution, page_count, char_count, model_used,
                   status, truncated, result_json, created_at,
                   coordinator_summary, preliminary_recommendation,
                   recommendation_reasoning
            FROM evaluations
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [_row_to_dict(r) for r in rows]


def get_evaluation_by_id(record_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM evaluations WHERE id = ?", (record_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    # Parse result_json back to a Python dict so callers don't have to
    if d.get("result_json"):
        try:
            d["result_json"] = json.loads(d["result_json"])
        except (json.JSONDecodeError, TypeError):
            pass   # leave as string if unparseable
    # Parse coordinator_summary back to a dict
    if d.get("coordinator_summary"):
        try:
            d["coordinator_summary"] = json.loads(d["coordinator_summary"])
        except (json.JSONDecodeError, TypeError):
            pass
    d["truncated"] = bool(d.get("truncated", 0))
    return d


# ── Analytics helpers ──────────────────────────────────────────────────────────

def compute_analytics() -> Dict[str, Any]:
    """
    Compute aggregate statistics directly from the SQLite table.
    Returns a structure matching what the frontend Analytics view expects.
    All computation in SQL where possible; Python used only for derived values.
    """
    with _connect() as conn:

        # ── Totals ──
        totals_row = conn.execute(
            """
            SELECT
                COUNT(*)                                      AS proposals,
                SUM(CASE WHEN status='completed' THEN 1 END)  AS completed
            FROM evaluations
            """
        ).fetchone()

        proposals = totals_row["proposals"] or 0
        completed = totals_row["completed"] or 0

        if proposals == 0:
            return _empty_analytics()

        # ── Score statistics ──
        # We derive a simple overall score from the model output quality proxy:
        # presence of a non-empty title + idea + problem + solution each give 25 pts.
        # Stored as computed column via CASE expressions.
        score_rows = conn.execute(
            """
            SELECT
                (CASE WHEN title_or_topic    != '' AND title_or_topic    IS NOT NULL THEN 25 ELSE 0 END +
                 CASE WHEN main_idea         != '' AND main_idea         IS NOT NULL THEN 25 ELSE 0 END +
                 CASE WHEN main_problem      != '' AND main_problem      IS NOT NULL THEN 25 ELSE 0 END +
                 CASE WHEN proposed_solution != '' AND proposed_solution IS NOT NULL THEN 25 ELSE 0 END
                ) AS score
            FROM evaluations
            """
        ).fetchall()

        scores = [r["score"] for r in score_rows]
        avg_score = round(sum(scores) / len(scores)) if scores else 0
        max_score = max(scores) if scores else 0
        min_score = min(scores) if scores else 0

        # ── Score distribution ──
        def _band(s: int) -> str:
            if s >= 90: return "90-100"
            if s >= 80: return "80-89"
            if s >= 70: return "70-79"
            if s >= 60: return "60-69"
            return "50-59"

        band_counts: Dict[str, int] = {
            "90-100": 0, "80-89": 0, "70-79": 0, "60-69": 0, "50-59": 0
        }
        for s in scores:
            band_counts[_band(s)] += 1

        score_distribution = [
            {"label": k, "count": v} for k, v in band_counts.items()
        ]

        # ── Truncation as rough risk proxy ──
        # truncated=1 → high risk (incomplete input)
        # score < 75  → medium risk
        # else        → low risk
        risk_rows = conn.execute(
            """
            SELECT
                truncated,
                (CASE WHEN title_or_topic    != '' AND title_or_topic    IS NOT NULL THEN 25 ELSE 0 END +
                 CASE WHEN main_idea         != '' AND main_idea         IS NOT NULL THEN 25 ELSE 0 END +
                 CASE WHEN main_problem      != '' AND main_problem      IS NOT NULL THEN 25 ELSE 0 END +
                 CASE WHEN proposed_solution != '' AND proposed_solution IS NOT NULL THEN 25 ELSE 0 END
                ) AS score
            FROM evaluations
            """
        ).fetchall()

        risk_breakdown = {"low": 0, "medium": 0, "high": 0}
        for r in risk_rows:
            if r["truncated"]:
                risk_breakdown["high"] += 1
            elif r["score"] < 75:
                risk_breakdown["medium"] += 1
            else:
                risk_breakdown["low"] += 1

        # ── Monthly volume ──
        month_rows = conn.execute(
            """
            SELECT
                SUBSTR(created_at, 1, 7) AS ym,
                COUNT(*)                  AS count
            FROM evaluations
            GROUP BY ym
            ORDER BY ym ASC
            LIMIT 12
            """
        ).fetchall()

        monthly_volume = [
            {"month": _fmt_month(r["ym"]), "count": r["count"]}
            for r in month_rows
        ]

        # ── By model ──
        model_rows = conn.execute(
            """
            SELECT model_used, COUNT(*) AS count
            FROM evaluations
            GROUP BY model_used
            ORDER BY count DESC
            """
        ).fetchall()

        by_model = [
            {"model": r["model_used"] or "unknown", "count": r["count"]}
            for r in model_rows
        ]

        # ── Top 5 most recent ──
        top_rows = conn.execute(
            """
            SELECT id, filename, title_or_topic, created_at,
                   (CASE WHEN title_or_topic    != '' THEN 25 ELSE 0 END +
                    CASE WHEN main_idea         != '' THEN 25 ELSE 0 END +
                    CASE WHEN main_problem      != '' THEN 25 ELSE 0 END +
                    CASE WHEN proposed_solution != '' THEN 25 ELSE 0 END
                   ) AS score
            FROM evaluations
            ORDER BY score DESC, created_at DESC
            LIMIT 5
            """
        ).fetchall()

        top_evaluations = [dict(r) for r in top_rows]

        # ── Recommendation breakdown ──
        rec_rows = conn.execute(
            """
            SELECT
                COALESCE(preliminary_recommendation, 'Not evaluated') AS rec,
                COUNT(*) AS count
            FROM evaluations
            GROUP BY preliminary_recommendation
            ORDER BY count DESC
            """
        ).fetchall()

        recommendation_breakdown = [
            {"recommendation": r["rec"], "count": r["count"]}
            for r in rec_rows
        ]

    return {
        "totals": {
            "proposals":   proposals,
            "completed":   completed,
        },
        "scores": {
            "avg_overall": avg_score,
            "highest":     max_score,
            "lowest":      min_score,
        },
        "risk_breakdown":          risk_breakdown,
        "score_distribution":      score_distribution,
        "monthly_volume":          monthly_volume,
        "by_model":                by_model,
        "top_evaluations":         top_evaluations,
        "recommendation_breakdown": recommendation_breakdown,
    }


def _empty_analytics() -> Dict[str, Any]:
    """Return a zeroed-out analytics structure when the table is empty."""
    return {
        "totals": {"proposals": 0, "completed": 0},
        "scores": {"avg_overall": 0, "highest": 0, "lowest": 0},
        "risk_breakdown":     {"low": 0, "medium": 0, "high": 0},
        "score_distribution": [
            {"label": "90-100", "count": 0},
            {"label": "80-89",  "count": 0},
            {"label": "70-79",  "count": 0},
            {"label": "60-69",  "count": 0},
            {"label": "50-59",  "count": 0},
        ],
        "monthly_volume":           [],
        "by_model":                 [],
        "top_evaluations":          [],
        "recommendation_breakdown": [],
    }


def _fmt_month(ym: str) -> str:
    """Convert '2024-11' to 'Nov 2024'."""
    try:
        dt = datetime.strptime(ym, "%Y-%m")
        return dt.strftime("%b %Y")
    except ValueError:
        return ym
