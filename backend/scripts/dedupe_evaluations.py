#!/usr/bin/env python3
"""
Deduplicate evaluation records by filename.

Rules (applied PER FILENAME):
  1. Keep records with human review (reviewer_final_decision NOT NULL)
  2. Then keep records with dates 2026-09-28 to 2026-10-06
  3. Then keep newest (created_at DESC)

Scope:
  - Processes demo evaluation files (7 known filenames)
  - Never touches r.pdf or RnD_actual_file_check.pdf
  - Keeps exactly 1 record per demo filename

Usage:
  python scripts/dedupe_evaluations.py           # dry-run (shows what will be deleted)
  python scripts/dedupe_evaluations.py --apply   # actually delete
"""
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "evaluations.db"

TARGET_DATE_START = "2026-09-28"
TARGET_DATE_END = "2026-10-06"

# Demo evaluation filenames (seeded by seed_demo.py)
DEMO_FILENAMES = [
    "solar_water_purification.pdf",
    "federated_learning_hospitals.pdf",
    "soil_sensor_network.pdf",
    "quantum_safe_encryption.pdf",
    "ai_crop_yield_forecasting.pdf",
    "wearable_ecg_monitor.pdf",
    "battery_recycling_process.pdf",
]


def score_record(record):
    """
    Score a record for keep priority (higher = better).
    Returns: (has_review, in_date_range, created_at)
    """
    record_id, filename, created_at, reviewer_decision, is_demo = record
    
    # Extract date from ISO timestamp
    date_str = created_at[:10] if created_at else "0000-00-00"
    
    has_review = 1 if reviewer_decision else 0
    in_date_range = 1 if TARGET_DATE_START <= date_str <= TARGET_DATE_END else 0
    
    return (has_review, in_date_range, created_at)


def group_by_filename(conn):
    """Group demo evaluation records by filename."""
    cursor = conn.cursor()
    
    # Only get demo evaluation files
    placeholders = ','.join('?' * len(DEMO_FILENAMES))
    cursor.execute(f"""
        SELECT id, filename, created_at, reviewer_final_decision, is_demo
        FROM evaluations
        WHERE filename IN ({placeholders})
        ORDER BY filename, created_at DESC
    """, DEMO_FILENAMES)
    
    all_records = cursor.fetchall()
    
    # Group by filename
    groups = {}
    for record in all_records:
        record_id, filename, created_at, reviewer_decision, is_demo = record
        if filename not in groups:
            groups[filename] = []
        groups[filename].append(record)
    
    return groups


def find_duplicates(groups):
    """Identify duplicate groups (more than 1 record per filename)."""
    duplicates = {}
    
    for filename, records in groups.items():
        if len(records) > 1:
            duplicates[filename] = records
    
    return duplicates


def main():
    apply = '--apply' in sys.argv
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # Get total counts
    cursor.execute("SELECT COUNT(*) FROM evaluations")
    total_count = cursor.fetchone()[0]
    
    # Count demo files
    placeholders = ','.join('?' * len(DEMO_FILENAMES))
    cursor.execute(f"SELECT COUNT(*) FROM evaluations WHERE filename IN ({placeholders})", DEMO_FILENAMES)
    demo_file_count = cursor.fetchone()[0]
    
    # Count non-demo files (r.pdf, etc)
    cursor.execute(f"SELECT COUNT(*) FROM evaluations WHERE filename NOT IN ({placeholders})", DEMO_FILENAMES)
    non_demo_file_count = cursor.fetchone()[0]
    
    print(f"\n{'='*80}")
    print(f"CURRENT STATE")
    print(f"{'='*80}")
    print(f"  Demo evaluation records (7 filenames): {demo_file_count}")
    print(f"  Other records (r.pdf, etc):            {non_demo_file_count}")
    print(f"  Total:                                 {total_count}")
    
    # Group records
    groups = group_by_filename(conn)
    duplicates = find_duplicates(groups)
    
    # Display duplicates and determine what to delete
    if not duplicates:
        print(f"\n{'='*80}")
        print(f"✓ No duplicates found in demo evaluation files")
        print(f"{'='*80}\n")
        conn.close()
        return
    
    print(f"\n{'='*80}")
    if apply:
        print(f"APPLYING DEDUPLICATION: Demo evaluation files")
    else:
        print(f"DRY RUN: The following demo records would be processed:")
    print(f"{'='*80}\n")
    
    to_delete = []
    
    for filename, records in duplicates.items():
        print(f"  Filename: {filename}")
        print(f"  Count:    {len(records)} records\n")
        
        # Sort by priority (has_review DESC, in_date_range DESC, created_at DESC)
        sorted_records = sorted(records, key=score_record, reverse=True)
        
        keep_record = sorted_records[0]
        delete_records = sorted_records[1:]
        
        # Display KEEP
        record_id, fn, created_at, reviewer_decision, is_demo = keep_record
        date_str = created_at[:10] if created_at else "N/A"
        review_status = "✓ Reviewed" if reviewer_decision else "Not reviewed"
        in_range = TARGET_DATE_START <= date_str <= TARGET_DATE_END
        range_status = "✓ In range" if in_range else "Out of range"
        demo_flag = f"is_demo={is_demo}"
        
        print(f"    [KEEP] ID: {record_id[:12]}... | {date_str} | {review_status} | {range_status} | {demo_flag}")
        
        # Display DELETE
        for record in delete_records:
            record_id, fn, created_at, reviewer_decision, is_demo = record
            date_str = created_at[:10] if created_at else "N/A"
            review_status = "✓ Reviewed" if reviewer_decision else "Not reviewed"
            in_range = TARGET_DATE_START <= date_str <= TARGET_DATE_END
            range_status = "✓ In range" if in_range else "Out of range"
            demo_flag = f"is_demo={is_demo}"
            
            print(f"    [DELETE] ID: {record_id[:12]}... | {date_str} | {review_status} | {range_status} | {demo_flag}")
            to_delete.append(record_id)
        
        print()
    
    print(f"{'='*80}")
    print(f"  Total demo records to delete:  {len(to_delete)}")
    print(f"  Demo records after cleanup:    {demo_file_count - len(to_delete)} (expected: 7)")
    print(f"  Non-demo records (unchanged):  {non_demo_file_count}")
    print(f"{'='*80}\n")
    
    if not apply:
        print("This was a DRY RUN. No changes were made.")
        print("To actually delete these records, run:")
        print("  python scripts/dedupe_evaluations.py --apply")
    else:
        # Actually delete
        if to_delete:
            placeholders = ','.join('?' * len(to_delete))
            cursor.execute(f"DELETE FROM evaluations WHERE id IN ({placeholders})", to_delete)
            conn.commit()
            
            print(f"✓ Deleted {len(to_delete)} duplicate demo record(s).")
        
        # Verify final state
        cursor.execute(f"SELECT COUNT(*) FROM evaluations WHERE filename IN ({','.join('?' * len(DEMO_FILENAMES))})", DEMO_FILENAMES)
        final_demo_count = cursor.fetchone()[0]
        
        cursor.execute(f"SELECT COUNT(*) FROM evaluations WHERE filename NOT IN ({','.join('?' * len(DEMO_FILENAMES))})", DEMO_FILENAMES)
        final_non_demo_count = cursor.fetchone()[0]
        
        # Count per filename
        cursor.execute("""
            SELECT filename, COUNT(*) as count
            FROM evaluations
            GROUP BY filename
            ORDER BY filename
        """)
        
        print(f"\n{'='*80}")
        print(f"FINAL STATE")
        print(f"{'='*80}")
        print(f"  Demo evaluation records (7 filenames): {final_demo_count}")
        print(f"  Other records (r.pdf, etc):            {final_non_demo_count}")
        print(f"  Total:                                 {final_demo_count + final_non_demo_count}")
        print(f"\n  Records per filename:")
        for row in cursor.fetchall():
            print(f"    {row[1]}x {row[0]}")
        print(f"{'='*80}\n")
    
    conn.close()


if __name__ == "__main__":
    main()
