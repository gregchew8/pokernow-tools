#!/usr/bin/env python3
import os
import re
import csv
import sys
import time
import subprocess
import requests
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

def run_applescript(script):
    process = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True
    )
    if process.returncode != 0:
        raise Exception(f"AppleScript Error: {process.stderr.strip()}")
    return process.stdout.strip()

def extract_game_ids(text):
    return re.findall(r"pokernow\.club/games/(pgl[a-zA-Z0-9\-]+)", text)

def parse_date_from_iso(iso_str):
    if not iso_str:
        return None
    match = re.match(r"(\d{4}-\d{2}-\d{2})", iso_str)
    if match:
        return match.group(1)
    return None

def main():
    load_env()
    db = DBClient()
    
    # 1. Fetch existing session filenames to extract game IDs
    cursor = db.execute("SELECT filename FROM sessions")
    existing_filenames = [r[0] if db.is_postgres else r["filename"] for r in cursor.fetchall()]
    existing_ids = set()
    for fn in existing_filenames:
        match = re.search(r"ledger_(pgl[a-zA-Z0-9\-]+)\.csv", fn)
        if match:
            existing_ids.add(match.group(1))
    print(f"Loaded {len(existing_ids)} existing game IDs from the database.")

    print("\n" + "="*80)
    print(" PREPARATION REQUIRED:")
    print(" 1. Please open your regular personal Google Chrome browser on your Mac Mini.")
    print(" 2. Navigate to: https://groups.google.com/g/lcr-poker")
    print(" 3. Make sure you are logged in and can see the list of threads/topics.")
    print(" 4. Scroll down the list of topics as far as you can to load historical games.")
    print(" 5. KEEP Chrome open as the front window.")
    print("="*80 + "\n")
    
    input("Once you have Chrome open at the Google Group topic list, press [Enter] to start scraping...")

    print("\nScraping thread links from Chrome active tab...")
    
    # Query all thread link URLs from the current page without using double quotes (escaped for AppleScript)
    js_get_links = "var arr = []; var links = document.getElementsByTagName('a'); for (var i=0; i<links.length; i++) { if (links[i].href.indexOf('/g/lcr-poker/c/') !== -1) arr.push(links[i].href); } arr.join('\\\\n');"
    applescript_get_links = f'''
        tell application "Google Chrome"
            tell active tab of front window
                execute javascript "{js_get_links}"
            end tell
        end tell
    '''
    
    try:
        links_output = run_applescript(applescript_get_links)
        thread_urls = [line.strip() for line in links_output.splitlines() if line.strip()]
        thread_urls = list(set(thread_urls))
    except Exception as e:
        print(f"Failed to scrape thread links: {e}")
        print("Please verify that Chrome allows JavaScript from Apple Events.")
        print("To enable this, in Chrome go to: View > Developer > Allow JavaScript from Apple Events")
        sys.exit(1)

    print(f"Found {len(thread_urls)} unique topic threads to scrape.")
    if not thread_urls:
        print("No threads found. Make sure the frontmost Chrome tab is open at the Google Groups list.")
        return

    all_game_ids = set()
    
    # Navigate the active tab to each thread and grab the text
    for idx, t_url in enumerate(thread_urls):
        print(f"[{idx+1}/{len(thread_urls)}] Navigating to: {t_url}")
        applescript_navigate = f'''
            tell application "Google Chrome"
                tell active tab of front window
                    set URL to "{t_url}"
                end tell
            end tell
        '''
        run_applescript(applescript_navigate)
        time.sleep(3.5) # Wait for page to load
        
        applescript_get_text = '''
            tell application "Google Chrome"
                tell active tab of front window
                    execute javascript "document.body.innerText"
                end tell
            end tell
        '''
        try:
            body_text = run_applescript(applescript_get_text)
            game_ids = extract_game_ids(body_text)
            for gid in game_ids:
                all_game_ids.add(gid)
        except Exception as e:
            print(f"Error reading thread content: {e}")
            
    print(f"\nExtracted {len(all_game_ids)} total Poker Now game links.")
    new_game_ids = [gid for gid in all_game_ids if gid not in existing_ids]
    print(f"Found {len(new_game_ids)} new game sessions to import.")
    
    if not new_game_ids:
        print("No new games to import. Done.")
        return
        
    # Download and import each new game
    imported_count = 0
    base_url = "https://www.pokernow.club/games/{}/ledger_{}.csv"
    
    for idx, gid in enumerate(new_game_ids):
        print(f"\n[{idx+1}/{len(new_game_ids)}] Downloading ledger for game: {gid}...")
        url = base_url.format(gid, gid)
        try:
            res = requests.get(url, timeout=10)
            res.raise_for_status()
            
            # Parse CSV content to get start date and rows
            lines = res.text.splitlines()
            reader = csv.DictReader(lines)
            rows = list(reader)
            
            if not rows:
                print(f"Warning: Ledger for {gid} is empty. Skipping.")
                continue
                
            # Get ledger date from the first row's start time
            first_start = rows[0].get("session_start_at")
            ledger_date = parse_date_from_iso(first_start)
            if not ledger_date:
                print(f"Warning: Could not parse date for {gid} from timestamp {first_start}. Skipping.")
                continue
                
            # Insert Session
            session_filename = f"ledger_{gid}.csv"
            
            # Check if this date already exists in database
            date_exists = db.execute("SELECT ledger_date FROM sessions WHERE ledger_date = %s" if db.is_postgres else "SELECT ledger_date FROM sessions WHERE ledger_date = ?", (ledger_date,)).fetchone()
            if not date_exists:
                db.insert_session(ledger_date, session_filename)
                
            # Insert Records
            records_inserted = 0
            for row in rows:
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
                    print(f"Error parsing numeric fields in row for {nickname}: {e}. Skipping row.")
                    continue
                    
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
                    records_inserted += 1
                    
            print(f"Imported game {gid} as session '{ledger_date}'. Inserted {records_inserted} player records.")
            imported_count += 1
            
        except Exception as e:
            print(f"Failed to import game {gid}: {e}")
            
    print(f"\nImport finished! Successfully imported {imported_count} new historical games.")

if __name__ == "__main__":
    main()
