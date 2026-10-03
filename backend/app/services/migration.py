"""
migration.py — Safe, additive SQLite schema migrations.

Each migration function uses ALTER TABLE … ADD COLUMN guarded by a check
against the existing column list (sqlite3 raises an error if you try to
ADD a column that already exists, so we check first).

run_migrations() is called from main.py startup AFTER init_db(), so it is
safe to call on a fresh DB (all columns already exist) or on an existing DB
that was created before these columns were added.

No data is modified — purely additive DDL.
"""
import sqlite3
import logging
from app.services.database import _connect

logger = logging.getLogger(__name__)


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """Return True if `column` already exists on `table`."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _add_column_if_missing(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    """ADD COLUMN only when it doesn't already exist."""
    if not _column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        logger.info("Migration: added column %s.%s", table, column)
    else:
        logger.debug("Migration: column %s.%s already exists — skipped", table, column)


def run_migrations() -> None:
    """
    Apply all pending schema migrations to the evaluations table.

    Brick 7 migrations:
        coordinator_summary, preliminary_recommendation, recommendation_reasoning

    Brick 8 migrations:
        novelty_score, technical_score, financial_score, impact_score
        overall_score, score_band
        reviewer_overrides, reviewer_final_decision, reviewer_notes,
        reviewer_updated_at
    """
    with _connect() as conn:
        # ── Brick 7 ───────────────────────────────────────────────────────────
        _add_column_if_missing(conn, "evaluations", "coordinator_summary",
                               "TEXT DEFAULT NULL")
        _add_column_if_missing(conn, "evaluations", "preliminary_recommendation",
                               "TEXT DEFAULT NULL")
        _add_column_if_missing(conn, "evaluations", "recommendation_reasoning",
                               "TEXT DEFAULT NULL")

        # ── Brick 8: AI score fields ──────────────────────────────────────────
        _add_column_if_missing(conn, "evaluations", "novelty_score",
                               "INTEGER DEFAULT NULL")
        _add_column_if_missing(conn, "evaluations", "technical_score",
                               "INTEGER DEFAULT NULL")
        _add_column_if_missing(conn, "evaluations", "financial_score",
                               "INTEGER DEFAULT NULL")
        _add_column_if_missing(conn, "evaluations", "impact_score",
                               "INTEGER DEFAULT NULL")
        _add_column_if_missing(conn, "evaluations", "overall_score",
                               "REAL DEFAULT NULL")
        _add_column_if_missing(conn, "evaluations", "score_band",
                               "TEXT DEFAULT NULL")

        # ── Brick 8: reviewer fields ──────────────────────────────────────────
        _add_column_if_missing(conn, "evaluations", "reviewer_overrides",
                               "TEXT DEFAULT NULL")        # JSON-encoded dict
        _add_column_if_missing(conn, "evaluations", "reviewer_final_decision",
                               "TEXT DEFAULT NULL")        # Approve | Revise | Reject
        _add_column_if_missing(conn, "evaluations", "reviewer_notes",
                               "TEXT DEFAULT NULL")
        _add_column_if_missing(conn, "evaluations", "reviewer_updated_at",
                               "TEXT DEFAULT NULL")        # ISO-8601 UTC timestamp

        conn.commit()

    logger.info("run_migrations() complete")
