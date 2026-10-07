#!/usr/bin/env python3
"""
Delete RnD_actual_file_check.pdf records from evaluations database.

Usage:
  python delete_rnd_actual.py           # dry-run (shows what will be deleted)
  python delete_rnd_actual.py --apply   # actually delete
"""
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "evaluations.db"

TARGET_FILENAME = "RnD_actual_file_check.pdf"


def main():
    apply = '--apply' in sys.argv
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # Get total count before
    cursor.execute("SELECT COUNT(*) FROM evaluations")
    total_before = cursor.fetchone()[0]
    
    # Find matching records
    cursor.execute("""
        SELECT id, filename, created_at, overall_score, is_demo
        FROM evaluations
        WHERE filename = ?
        ORDER BY created_at DESC
    """, (TARGET_FILENAME,))
    
    records = cursor.fetchall()
    
    print(f"\n{'='*80}")
    print(f"CURRENT STATE")
    print(f"{'='*80}")
    print(f"  Total records in database: {total_before}")
    print()
    
    if not records:
        print(f"✓ No records found with filename '{TARGET_FILENAME}'")
        conn.close()
        return
    
    # Display what will be/was deleted
    print(f"{'='*80}")
    if apply:
        print(f"DELETING: Records with filename '{TARGET_FILENAME}'")
    else:
        print(f"DRY RUN: The following records would be deleted:")
    print(f"{'='*80}\n")
    
    for record in records:
        record_id, filename, created_at, score, is_demo = record
        date_str = created_at[:10] if created_at else "N/A"
        score_str = f"{score:.2f}" if score else "N/A"
        demo_flag = f"is_demo={is_demo}"
        
        print(f"  ID:       {record_id[:16]}...")
        print(f"  Filename: {filename}")
        print(f"  Date:     {date_str}")
        print(f"  Score:    {score_str}")
        print(f"  Flag:     {demo_flag}")
        print(f"  {'-'*76}")
    
    print(f"\nTotal matching records: {len(records)}")
    print(f"Expected after deletion: {total_before - len(records)}")
    print(f"{'='*80}\n")
    
    if not apply:
        print("This was a DRY RUN. No changes were made.")
        print("To actually delete these records, run:")
        print("  python delete_rnd_actual.py --apply")
    else:
        # Actually delete
        cursor.execute("DELETE FROM evaluations WHERE filename = ?", (TARGET_FILENAME,))
        conn.commit()
        
        # Verify deletion
        cursor.execute("SELECT COUNT(*) FROM evaluations WHERE filename = ?", (TARGET_FILENAME,))
        remaining = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM evaluations")
        total_after = cursor.fetchone()[0]
        
        print(f"✓ Successfully deleted {len(records)} record(s).")
        print(f"\n{'='*80}")
        print(f"FINAL STATE")
        print(f"{'='*80}")
        print(f"  Records before:  {total_before}")
        print(f"  Records deleted: {len(records)}")
        print(f"  Records after:   {total_after}")
        print(f"  Remaining '{TARGET_FILENAME}' records: {remaining}")
        print(f"{'='*80}\n")
        
        if remaining > 0:
            print(f"⚠ Warning: {remaining} records with filename '{TARGET_FILENAME}' still remain!")
        
        # Show breakdown by filename
        cursor.execute("""
            SELECT filename, COUNT(*) as count
            FROM evaluations
            GROUP BY filename
            ORDER BY count DESC, filename ASC
        """)
        
        print("Records by filename:")
        for row in cursor.fetchall():
            print(f"  {row[1]:2}x {row[0]}")
    
    conn.close()


if __name__ == "__main__":
    main()
