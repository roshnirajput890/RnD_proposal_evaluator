#!/usr/bin/env python3
"""
Database cleanup script for R&D proposal evaluations.

Removes:
  1. Failed evaluations (status='failed')
  2. Parsing failures (title contains "Analysis parsing failed")
  3. Insufficient information (score_band = "Insufficient Information")
  4. Duplicate r.pdf runs (keeps only the NEWEST)
  5. Duplicate RnD_actual_file_check.pdf runs (keeps only the NEWEST with all agents succeeded)

Always keeps the best/newest RnD_actual_file_check.pdf record.

Usage:
  python scripts/cleanup_db.py           # dry-run (shows what would be deleted)
  python scripts/cleanup_db.py --apply   # actually delete records
"""
import sqlite3
import sys
import json
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "evaluations.db"


def check_agent_success(result_json_str):
    """
    Parse result_json and check if all 4 scoring agents succeeded.
    Returns True if all agents have scores, False otherwise.
    """
    if not result_json_str:
        return False
    try:
        result = json.loads(result_json_str)
        agent_statuses = result.get('_agent_statuses', {})
        
        # Check the 4 scoring agents
        required_agents = ['novelty_agent', 'technical_agent', 'financial_agent', 'impact_agent']
        for agent in required_agents:
            if agent_statuses.get(agent) != 'completed':
                return False
        return True
    except (json.JSONDecodeError, KeyError):
        return False


def get_records_to_delete(conn, dry_run=True):
    """Identify records to delete according to cleanup rules."""
    cursor = conn.cursor()
    to_delete = []
    
    # Rule 1: Failed evaluations
    cursor.execute("SELECT id, filename, created_at FROM evaluations WHERE status='failed'")
    failed = cursor.fetchall()
    for row in failed:
        to_delete.append({
            'id': row[0],
            'filename': row[1],
            'created_at': row[2],
            'reason': 'Status: failed'
        })
    
    # Rule 2: Analysis parsing failed
    cursor.execute("""
        SELECT id, filename, created_at 
        FROM evaluations 
        WHERE title_or_topic LIKE '%Analysis parsing failed%'
    """)
    parse_failed = cursor.fetchall()
    for row in parse_failed:
        to_delete.append({
            'id': row[0],
            'filename': row[1],
            'created_at': row[2],
            'reason': 'Analysis parsing failed'
        })
    
    # Rule 3: Insufficient Information
    cursor.execute("""
        SELECT id, filename, created_at 
        FROM evaluations 
        WHERE score_band = 'Insufficient Information'
    """)
    insufficient = cursor.fetchall()
    for row in insufficient:
        to_delete.append({
            'id': row[0],
            'filename': row[1],
            'created_at': row[2],
            'reason': 'Insufficient Information'
        })
    
    # Rule 4: Duplicate r.pdf records (keep only NEWEST)
    cursor.execute("""
        SELECT id, filename, created_at, result_json
        FROM evaluations 
        WHERE filename = 'r.pdf'
        ORDER BY created_at DESC
    """)
    r_pdf_records = cursor.fetchall()
    if len(r_pdf_records) > 1:
        # Keep the first (newest), mark rest for deletion
        for row in r_pdf_records[1:]:
            to_delete.append({
                'id': row[0],
                'filename': row[1],
                'created_at': row[2],
                'reason': 'Duplicate r.pdf (keeping newest)'
            })
    
    # Rule 5: Duplicate RnD_actual_file_check.pdf (keep NEWEST with all agents succeeded)
    cursor.execute("""
        SELECT id, filename, created_at, result_json, title_or_topic
        FROM evaluations 
        WHERE filename = 'RnD_actual_file_check.pdf'
        ORDER BY created_at DESC
    """)
    actual_records = cursor.fetchall()
    
    if len(actual_records) > 1:
        # Find the best record: newest with all agents succeeded
        best_record = None
        for row in actual_records:
            if check_agent_success(row[3]):
                best_record = row
                break
        
        # If no record has all agents succeeded, keep the newest anyway
        if best_record is None:
            best_record = actual_records[0]
        
        # Mark all others for deletion
        for row in actual_records:
            if row[0] != best_record[0]:
                to_delete.append({
                    'id': row[0],
                    'filename': row[1],
                    'created_at': row[2],
                    'reason': f'Duplicate RnD_actual_file_check.pdf (keeping best: {best_record[0][:8]}...)'
                })
    
    return to_delete


def main():
    dry_run = '--apply' not in sys.argv
    
    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)
    
    conn = sqlite3.connect(str(DB_PATH))
    
    # Get total count before cleanup
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM evaluations")
    total_before = cursor.fetchone()[0]
    
    # Identify records to delete
    to_delete = get_records_to_delete(conn, dry_run)
    
    # Remove duplicates (same ID might match multiple rules)
    unique_ids = {}
    for record in to_delete:
        if record['id'] not in unique_ids:
            unique_ids[record['id']] = record
    
    to_delete = list(unique_ids.values())
    
    if not to_delete:
        print("✓ No records to delete. Database is clean.")
        conn.close()
        return
    
    # Display what will be deleted
    print(f"\n{'='*80}")
    if dry_run:
        print("DRY RUN: The following records WOULD BE deleted:")
    else:
        print("APPLYING CLEANUP: The following records WILL BE deleted:")
    print(f"{'='*80}\n")
    
    for record in to_delete:
        print(f"  ID: {record['id'][:12]}... | {record['filename']:30} | {record['created_at'][:19]} | {record['reason']}")
    
    print(f"\n{'='*80}")
    print(f"Total records before: {total_before}")
    print(f"Records to delete:    {len(to_delete)}")
    print(f"Records after:        {total_before - len(to_delete)}")
    print(f"{'='*80}\n")
    
    if dry_run:
        print("This was a DRY RUN. No changes were made.")
        print("To actually delete these records, run:")
        print("  python scripts/cleanup_db.py --apply")
    else:
        # Actually delete the records
        for record in to_delete:
            cursor.execute("DELETE FROM evaluations WHERE id = ?", (record['id'],))
        
        conn.commit()
        
        # Verify
        cursor.execute("SELECT COUNT(*) FROM evaluations")
        total_after = cursor.fetchone()[0]
        
        print(f"✓ Cleanup complete. Deleted {len(to_delete)} records.")
        print(f"  Records remaining: {total_after}")
    
    conn.close()


if __name__ == "__main__":
    main()
