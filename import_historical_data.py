#!/usr/bin/env python3
import os
import re
import csv
from db_client import DBClient

WORKING_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(WORKING_DIR, "output")

def parse_date_from_filename(filename):
    # E.g. downloaded_ledgers_20250628.csv -> 2025-06-28
    match = re.search(r"downloaded_ledgers_(\d{4})(\d{2})(\d{2})\.csv", filename)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return None

def import_historical_data():
    db = DBClient()
    
    if not os.path.exists(OUTPUT_DIR):
        print(f"[Importer] Error: Output directory {OUTPUT_DIR} does not exist.")
        return

    files = sorted([f for f in os.listdir(OUTPUT_DIR) if f.startswith("downloaded_ledgers_") and f.endswith(".csv")])
    print(f"[Importer] Found {len(files)} historical ledger CSV files.")

    total_sessions_imported = 0
    total_records_imported = 0

    for filename in files:
        ledger_date = parse_date_from_filename(filename)
        if not ledger_date:
            print(f"[Importer] Skipping file with unrecognized date format: {filename}")
            continue

        filepath = os.path.join(OUTPUT_DIR, filename)
        
        # 1. Insert session
        inserted_session = db.insert_session(ledger_date, filename)
        if inserted_session:
            total_sessions_imported += 1
            print(f"[Importer] Importing session: {ledger_date} ({filename})")
        else:
            # Session already existed, but let's check for missing records in it anyway
            pass

        # 2. Read CSV and insert records
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                
                # Check for standard columns
                required_cols = ["player_nickname", "player_id", "session_start_at", "buy_in", "net"]
                if not all(col in reader.fieldnames for col in required_cols):
                    print(f"[Importer] Error: CSV {filename} missing required columns. Skipping.")
                    continue

                for row in reader:
                    nickname = row.get("player_nickname")
                    player_id = row.get("player_id")
                    start_at = row.get("session_start_at")
                    end_at = row.get("session_end_at") or None
                    
                    try:
                        buy_in = int(row.get("buy_in") or 0)
                        
                        buy_out_str = row.get("buy_out")
                        buy_out = float(buy_out_str) if (buy_out_str and buy_out_str.strip()) else None
                        
                        stack_str = row.get("stack")
                        stack = int(stack_str) if (stack_str and stack_str.strip()) else None
                        
                        net = int(row.get("net") or 0)
                    except ValueError as e:
                        print(f"[Importer] Error parsing numeric values in row for {nickname} in {filename}: {e}. Skipping row.")
                        continue

                    # Insert record
                    inserted_rec = db.insert_ledger_record(
                        nickname=nickname,
                        player_id=player_id,
                        start_at=start_at,
                        end_at=end_at,
                        buy_in=buy_in,
                        buy_out=buy_out,
                        stack=stack,
                        net=net,
                        ledger_date=ledger_date
                    )
                    if inserted_rec:
                        total_records_imported += 1

        except Exception as e:
            print(f"[Importer] Failed to process {filename}: {e}")

    print(f"\n[Importer] Import completed!")
    print(f"[Importer] Sessions imported/verified: {len(files)}")
    print(f"[Importer] New records inserted: {total_records_imported}")

if __name__ == "__main__":
    import_historical_data()
