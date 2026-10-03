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

    Current migrations:
        coordinator_summary          TEXT   — JSON-encoded coordinator result dict
        preliminary_recommendation   TEXT   — "Recommend" | "Revise and Resubmit"
                                              | "Not Recommended"
                                              | "Insufficient Information"
        recommendation_reasoning     TEXT   — coordinator's explanation paragraph
    """
    with _connect() as conn:
        _add_column_if_missing(conn, "evaluations", "coordinator_summary",
                               "TEXT DEFAULT NULL")
        _add_column_if_missing(conn, "evaluations", "preliminary_recommendation",
                               "TEXT DEFAULT NULL")
        _add_column_if_missing(conn, "evaluations", "recommendation_reasoning",
                               "TEXT DEFAULT NULL")
        conn.commit()

    logger.info("run_migrations() complete")
