#!/usr/bin/env python3
"""
Migration: Add is_demo column to evaluations table.

Adds a boolean column `is_demo` (stored as INTEGER, 0 or 1) to mark sample
evaluations used for portfolio demonstrations. Existing records default to 0.

Run once: python scripts/migrate_add_is_demo.py
"""
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "evaluations.db"


def migrate():
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # Check if column already exists
    cursor.execute("PRAGMA table_info(evaluations)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if "is_demo" in columns:
        print("✓ Column 'is_demo' already exists. Migration skipped.")
        conn.close()
        return
    
    # Add the column with default value 0
    print("Adding 'is_demo' column to evaluations table...")
    cursor.execute("""
        ALTER TABLE evaluations
        ADD COLUMN is_demo INTEGER DEFAULT 0
    """)
    conn.commit()
    
    # Verify
    cursor.execute("SELECT COUNT(*) FROM evaluations WHERE is_demo = 0")
    count = cursor.fetchone()[0]
    
    print(f"✓ Migration complete. Column added with default 0.")
    print(f"  {count} existing records marked as is_demo=0 (real evaluations)")
    
    conn.close()


if __name__ == "__main__":
    migrate()
