#!/usr/bin/env python3
import os
import re
import json
import datetime
from db_client import DBClient

WORKING_DIR = os.path.dirname(os.path.abspath(__file__))

def load_env():
    env_file = os.path.join(WORKING_DIR, ".env")
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        key, val = line.split("=", 1)
                        os.environ[key.strip()] = val.strip().strip('"').strip("'")

def parse_date(text):
    # E.g. "Mar 26, 2022" or "March 26, 2022"
    months = {
        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
        "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
        "January": 1, "February": 2, "March": 3, "April": 4, "June": 6,
        "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12
    }
    # Match Month Day, Year
    match = re.search(r"([a-zA-Z]+)\s+(\d{1,2}),\s+(\d{4})", text)
    if match:
        m_str, d_str, y_str = match.groups()
        m_num = months.get(m_str[:3].title()) or months.get(m_str.title())
        if m_num:
            return f"{y_str}-{m_num:02d}-{int(d_str):02d}"
    return None

def parse_settlements(text):
    player_nets = {}
    lines = text.splitlines()
    current_winner = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Match winner line e.g., @Bartosz-Dabrowski requests $645.55 from: (handles optional @)
        winner_match = re.search(r"@?([\w\-\.]+)\s+requests\s+\$([0-9\.,]+)\s+from", line, re.IGNORECASE)
        if winner_match:
            current_winner = winner_match.group(1)
            if current_winner not in player_nets:
                player_nets[current_winner] = 0
            continue
            
        # Match payment line e.g., $12.54 @Steven-Trifon (handles optional @)
        payment_match = re.search(r"\$([0-9\.,]+)\s+@?([\w\-\.]+)", line)
        if payment_match and current_winner:
            amount_str, payer = payment_match.groups()
            amount_cents = int(round(float(amount_str.replace(",", "")) * 100))
            
            # Winner gains this amount
            player_nets[current_winner] = player_nets.get(current_winner, 0) + amount_cents
            # Payer loses this amount
            player_nets[payer] = player_nets.get(payer, 0) - amount_cents
            
    return player_nets

def main():
    load_env()
    db = DBClient()
    
    json_path = os.path.join(WORKING_DIR, "settlements.json")
    if not os.path.exists(json_path):
        print(f"Error: settlements.json not found at {json_path}")
        return
        
    with open(json_path, "r") as f:
        threads = json.load(f)
        
    print(f"Loaded {len(threads)} threads from settlements.json.")
    
    # Get existing session dates to filter duplicates
    cursor = db.execute("SELECT ledger_date FROM sessions")
    existing_dates = set(r[0] if db.is_postgres else r["ledger_date"] for r in cursor.fetchall())
    print(f"Found {len(existing_dates)} existing session dates in database.")
    
    imported_sessions = 0
    imported_records = 0
    
    for idx, thread in enumerate(threads):
        text = thread.get("text", "")
        url = thread.get("url", "")
        
        # 1. Parse date of the thread
        date_str = parse_date(text)
        if not date_str:
            # Try to get date from URL ID or skip
            continue
            
        # 2. Check duplicates
        if date_str in existing_dates:
            print(f"[{idx+1}/{len(threads)}] Skipping duplicate session on {date_str}.")
            continue
            
        # 3. Parse players and payments
        player_nets = parse_settlements(text)
        if not player_nets:
            continue
            
        # 4. Zero-sum verification
        total_sum = sum(player_nets.values())
        if total_sum != 0:
            print(f"[{idx+1}/{len(threads)}] Warning: Zero-sum mismatch on {date_str}. Total sum: ${total_sum/100:.2f}. Proceeding...")
            
        print(f"[{idx+1}/{len(threads)}] Importing session on {date_str} with {len(player_nets)} players...")
        
        # 5. Insert Session
        session_filename = f"google_groups_{date_str}.csv"
        db.insert_session(date_str, session_filename)
        existing_dates.add(date_str)
        imported_sessions += 1
        
        # 6. Insert Player Records
        for player, net_cents in player_nets.items():
            nickname = player
            player_id = player
            start_at = f"{date_str}T00:00:00Z"
            end_at = f"{date_str}T00:00:00Z"
            buy_in = 0
            buy_out = None
            stack = None
            net = net_cents
            
            inserted = db.insert_ledger_record(
                nickname=nickname,
                player_id=player_id,
                start_at=start_at,
                end_at=end_at,
                buy_in=buy_in,
                buy_out=buy_out,
                stack=stack,
                net=net,
                ledger_date=date_str
            )
            if inserted:
                imported_records += 1
                
        print(f"   Successfully imported {len(player_nets)} player records for {date_str}.")
        
    print(f"\nImport finished! Successfully imported {imported_sessions} new sessions with {imported_records} player records.")

if __name__ == "__main__":
    main()
