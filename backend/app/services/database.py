"""
database.py — SQLite persistence layer for evaluated proposals.

Schema (evaluations table — full current state including all migrations):
    id                        TEXT PRIMARY KEY
    filename                  TEXT NOT NULL
    title_or_topic            TEXT
    main_idea                 TEXT
    main_problem              TEXT
    proposed_solution         TEXT
    page_count                INTEGER
    char_count                INTEGER
    model_used                TEXT
    status                    TEXT DEFAULT 'completed'
    truncated                 INTEGER DEFAULT 0
    result_json               TEXT
    created_at                TEXT  (ISO-8601 UTC)

    -- Brick 7 coordinator fields --
    coordinator_summary       TEXT  (JSON-encoded dict)
    preliminary_recommendation TEXT
    recommendation_reasoning  TEXT

    -- Brick 8 AI score fields --
    novelty_score             INTEGER  (1-5 or NULL)
    technical_score           INTEGER
    financial_score           INTEGER
    impact_score              INTEGER
    overall_score             REAL     (weighted average or NULL)
    score_band                TEXT

    -- Brick 8 reviewer fields --
    reviewer_overrides        TEXT  (JSON-encoded dict)
    reviewer_final_decision   TEXT  (Approve | Revise | Reject)
    reviewer_notes            TEXT
    reviewer_updated_at       TEXT  (ISO-8601 UTC)
"""
import sqlite3
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── DB path ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent
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
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute(_CREATE_TABLE)
        conn.execute(_CREATE_IDX)
        conn.commit()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ── Write ──────────────────────────────────────────────────────────────────────

def save_evaluation(
    *,
    filename:          str,
    analysis:          Dict[str, Any],
    page_count:        int,
    char_count:        int,
    model_used:        str,
    full_result:       Dict[str, Any],
    # Brick 7
    coordinator_summary:         Optional[Dict[str, Any]] = None,
    preliminary_recommendation:  Optional[str] = None,
    recommendation_reasoning:    Optional[str] = None,
    # Brick 8 — AI scores
    novelty_score:    Optional[int]   = None,
    technical_score:  Optional[int]   = None,
    financial_score:  Optional[int]   = None,
    impact_score:     Optional[int]   = None,
    overall_score:    Optional[float] = None,
    score_band:       Optional[str]   = None,
    # Brick 9 — novelty search fields
    novelty_search_queries:  Optional[list]  = None,   # list[str]
    retrieved_papers:        Optional[list]  = None,   # list[dict]
    external_evidence_used:  Optional[bool]  = None,
) -> str:
    record_id  = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    truncated  = 1 if analysis.get("truncated") else 0

    coord_json = (
        json.dumps(coordinator_summary, ensure_ascii=False)
        if coordinator_summary else None
    )

    novelty_queries_json = (
        json.dumps(novelty_search_queries, ensure_ascii=False)
        if novelty_search_queries else None
    )
    retrieved_papers_json = (
        json.dumps(retrieved_papers, ensure_ascii=False)
        if retrieved_papers else None
    )
    external_evidence_int = (
        int(external_evidence_used)
        if external_evidence_used is not None else None
    )

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO evaluations (
                id, filename, title_or_topic, main_idea, main_problem,
                proposed_solution, page_count, char_count, model_used,
                status, truncated, result_json, created_at,
                coordinator_summary, preliminary_recommendation, recommendation_reasoning,
                novelty_score, technical_score, financial_score, impact_score,
                overall_score, score_band,
                novelty_search_queries, retrieved_papers, external_evidence_used
            ) VALUES (
                ?,?,?,?,?,?,?,?,?,'completed',?,?,?,
                ?,?,?,
                ?,?,?,?,?,?,
                ?,?,?
            )
            """,
            (
                record_id, filename,
                analysis.get("title_or_topic", ""),
                analysis.get("main_idea_summary", ""),
                analysis.get("main_problem", ""),
                analysis.get("proposed_solution", ""),
                page_count, char_count, model_used,
                truncated,
                json.dumps(full_result, ensure_ascii=False),
                created_at,
                coord_json, preliminary_recommendation, recommendation_reasoning,
                novelty_score, technical_score, financial_score, impact_score,
                overall_score, score_band,
                novelty_queries_json, retrieved_papers_json, external_evidence_int,
            ),
        )
        conn.commit()

    return record_id


def save_reviewer_override(
    record_id: str,
    *,
    reviewer_overrides:      Optional[Dict[str, Any]],
    reviewer_final_decision: Optional[str],
    reviewer_notes:          Optional[str],
) -> bool:
    """
    Update only the reviewer fields for an existing evaluation.
    AI scores are never touched.
    Returns True if a row was updated, False if record not found.
    """
    updated_at = datetime.now(timezone.utc).isoformat()
    overrides_json = (
        json.dumps(reviewer_overrides, ensure_ascii=False)
        if reviewer_overrides else None
    )

    with _connect() as conn:
        cur = conn.execute(
            """
            UPDATE evaluations
            SET reviewer_overrides      = ?,
                reviewer_final_decision = ?,
                reviewer_notes          = ?,
                reviewer_updated_at     = ?
            WHERE id = ?
            """,
            (overrides_json, reviewer_final_decision,
             reviewer_notes, updated_at, record_id),
        )
        conn.commit()
        return cur.rowcount > 0


# ── Read ───────────────────────────────────────────────────────────────────────

# All columns the SELECT statements should return
_ALL_COLS = """
    id, filename, title_or_topic, main_idea, main_problem,
    proposed_solution, page_count, char_count, model_used,
    status, truncated, result_json, created_at,
    coordinator_summary, preliminary_recommendation, recommendation_reasoning,
    novelty_score, technical_score, financial_score, impact_score,
    overall_score, score_band,
    reviewer_overrides, reviewer_final_decision, reviewer_notes,
    reviewer_updated_at,
    novelty_search_queries, retrieved_papers, external_evidence_used
"""


def get_evaluations(limit: int = 200) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT {_ALL_COLS} FROM evaluations ORDER BY created_at DESC LIMIT ?",
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

    # Parse JSON blobs back to Python objects
    for key in ("result_json", "coordinator_summary", "reviewer_overrides",
                "novelty_search_queries", "retrieved_papers"):
        if d.get(key):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                pass

    d["truncated"] = bool(d.get("truncated", 0))

    # Convert external_evidence_used integer → bool (None stays None)
    eeu = d.get("external_evidence_used")
    d["external_evidence_used"] = bool(eeu) if eeu is not None else None

    return d


# ── Analytics ──────────────────────────────────────────────────────────────────

def compute_analytics() -> Dict[str, Any]:
    with _connect() as conn:

        totals_row = conn.execute(
            """
            SELECT COUNT(*) AS proposals,
                   SUM(CASE WHEN status='completed' THEN 1 END) AS completed
            FROM evaluations
            """
        ).fetchone()

        proposals = totals_row["proposals"] or 0
        completed = totals_row["completed"] or 0

        if proposals == 0:
            return _empty_analytics()

        # ── Real overall scores from the DB ────────────────────────────────────
        score_rows = conn.execute(
            "SELECT overall_score, score_band FROM evaluations"
        ).fetchall()

        real_scores = [r["overall_score"] for r in score_rows if r["overall_score"] is not None]
        avg_score   = round(sum(real_scores) / len(real_scores), 2) if real_scores else 0
        max_score   = max(real_scores) if real_scores else 0
        min_score   = min(real_scores) if real_scores else 0

        # ── Score band distribution (real score_band column) ──────────────────
        band_labels = ["Recommend", "Revise and Resubmit", "Not Recommended",
                       "Insufficient Information", "Not scored"]
        band_counts: Dict[str, int] = {b: 0 for b in band_labels}
        for r in score_rows:
            b = r["score_band"] or "Not scored"
            if b not in band_counts:
                b = "Not scored"
            band_counts[b] += 1

        score_distribution = [
            {"label": k, "count": v}
            for k, v in band_counts.items()
            if v > 0
        ]

        # ── Per-category avg scores ────────────────────────────────────────────
        cat_row = conn.execute(
            """
            SELECT AVG(novelty_score)   AS avg_novelty,
                   AVG(technical_score) AS avg_technical,
                   AVG(financial_score) AS avg_financial,
                   AVG(impact_score)    AS avg_impact
            FROM evaluations
            WHERE novelty_score IS NOT NULL
               OR technical_score IS NOT NULL
               OR financial_score IS NOT NULL
               OR impact_score IS NOT NULL
            """
        ).fetchone()

        def _fmt_avg(v):
            return round(v, 2) if v is not None else None

        category_avg_scores = {
            "novelty":   _fmt_avg(cat_row["avg_novelty"]),
            "technical": _fmt_avg(cat_row["avg_technical"]),
            "financial": _fmt_avg(cat_row["avg_financial"]),
            "impact":    _fmt_avg(cat_row["avg_impact"]),
        }

        # ── Risk proxy (unchanged: uses truncated + overall_score) ─────────────
        risk_rows = conn.execute(
            "SELECT truncated, overall_score FROM evaluations"
        ).fetchall()

        risk_breakdown = {"low": 0, "medium": 0, "high": 0}
        for r in risk_rows:
            if r["truncated"]:
                risk_breakdown["high"] += 1
            elif (r["overall_score"] or 0) < 3.0:
                risk_breakdown["medium"] += 1
            else:
                risk_breakdown["low"] += 1

        # ── Monthly volume ─────────────────────────────────────────────────────
        month_rows = conn.execute(
            """
            SELECT SUBSTR(created_at,1,7) AS ym, COUNT(*) AS count
            FROM evaluations GROUP BY ym ORDER BY ym ASC LIMIT 12
            """
        ).fetchall()
        monthly_volume = [
            {"month": _fmt_month(r["ym"]), "count": r["count"]}
            for r in month_rows
        ]

        # ── By model ───────────────────────────────────────────────────────────
        model_rows = conn.execute(
            """
            SELECT model_used, COUNT(*) AS count
            FROM evaluations GROUP BY model_used ORDER BY count DESC
            """
        ).fetchall()
        by_model = [
            {"model": r["model_used"] or "unknown", "count": r["count"]}
            for r in model_rows
        ]

        # ── Top 5 by overall_score ─────────────────────────────────────────────
        top_rows = conn.execute(
            """
            SELECT id, filename, title_or_topic, created_at,
                   overall_score AS score, score_band
            FROM evaluations
            ORDER BY overall_score DESC NULLS LAST, created_at DESC
            LIMIT 5
            """
        ).fetchall()
        top_evaluations = [dict(r) for r in top_rows]

        # ── Recommendation breakdown (real score_band) ─────────────────────────
        rec_rows = conn.execute(
            """
            SELECT COALESCE(score_band, 'Not scored') AS rec, COUNT(*) AS count
            FROM evaluations GROUP BY score_band ORDER BY count DESC
            """
        ).fetchall()
        recommendation_breakdown = [
            {"recommendation": r["rec"], "count": r["count"]}
            for r in rec_rows
        ]

        # ── Reviewer stats ─────────────────────────────────────────────────────
        reviewer_row = conn.execute(
            """
            SELECT
                SUM(CASE WHEN reviewer_final_decision IS NOT NULL THEN 1 ELSE 0 END) AS reviewed,
                SUM(CASE WHEN reviewer_final_decision IS NULL     THEN 1 ELSE 0 END) AS pending
            FROM evaluations
            """
        ).fetchone()
        reviewer_stats = {
            "reviewed": reviewer_row["reviewed"] or 0,
            "pending":  reviewer_row["pending"]  or 0,
        }

    return {
        "totals":                 {"proposals": proposals, "completed": completed},
        "scores": {
            "avg_overall": avg_score,
            "highest":     max_score,
            "lowest":      min_score,
        },
        "category_avg_scores":    category_avg_scores,
        "risk_breakdown":         risk_breakdown,
        "score_distribution":     score_distribution,
        "monthly_volume":         monthly_volume,
        "by_model":               by_model,
        "top_evaluations":        top_evaluations,
        "recommendation_breakdown": recommendation_breakdown,
        "reviewer_stats":         reviewer_stats,
    }


def _empty_analytics() -> Dict[str, Any]:
    return {
        "totals":               {"proposals": 0, "completed": 0},
        "scores":               {"avg_overall": 0, "highest": 0, "lowest": 0},
        "category_avg_scores":  {"novelty": None, "technical": None,
                                 "financial": None, "impact": None},
        "risk_breakdown":       {"low": 0, "medium": 0, "high": 0},
        "score_distribution":   [],
        "monthly_volume":       [],
        "by_model":             [],
        "top_evaluations":      [],
        "recommendation_breakdown": [],
        "reviewer_stats":       {"reviewed": 0, "pending": 0},
    }


def _fmt_month(ym: str) -> str:
    try:
        return datetime.strptime(ym, "%Y-%m").strftime("%b %Y")
    except ValueError:
        return ym
