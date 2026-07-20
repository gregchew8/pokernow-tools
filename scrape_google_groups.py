#!/usr/bin/env python3
import os
import re
import csv
import time
import requests
import datetime
from db_client import DBClient

# Ensure Playwright uses the correct browser path
WORKING_DIR = os.path.dirname(os.path.abspath(__file__))
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(WORKING_DIR, "playwright-browsers")

from playwright.sync_api import sync_playwright

def extract_game_ids(text):
    # Matches URLs like pokernow.club/games/pgl...
    return re.findall(r"pokernow\.club/games/(pgl[a-zA-Z0-9\-]+)", text)

def parse_date_from_iso(iso_str):
    # E.g. "2025-06-28T03:15:00.000Z" -> "2025-06-28"
    if not iso_str:
        return None
    match = re.match(r"(\d{4}-\d{2}-\d{2})", iso_str)
    if match:
        return match.group(1)
    return None

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

    print("\nLaunching Chrome...")
    with sync_playwright() as p:
        # Launch headed browser using their existing profile so Google login might be preserved!
        profile_path = os.path.join(WORKING_DIR, "chrome-profile")
        context = p.chromium.launch_persistent_context(
            profile_path,
            headless=False,
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()
        
        print("Navigating to Google Groups...")
        page.goto("https://groups.google.com/g/lcr-poker")
        
        print("\n" + "="*80)
        print(" ACTION REQUIRED:")
        print(" Please check the opened Chrome browser window on your Mac screen.")
        print(" If you need to log in to your Google Account to view the Google Group, please do so now.")
        print(" Once you can see the Google Group topic list, press Enter here in the terminal...")
        print("="*80 + "\n")
        input("Press [Enter] to continue...")
        
        # Scrape thread links from the list
        print("Scraping threads...")
        # Scroll down multiple times to trigger infinite load to retrieve historical threads
        for i in range(12):
            page.evaluate("window.scrollBy(0, 1500)")
            time.sleep(1.2)
            
        links = page.locator("a[href*='/g/lcr-poker/c/']").all()
        thread_urls = []
        for link in links:
            url = link.get_attribute("href")
            if url:
                if not url.startswith("http"):
                    url = "https://groups.google.com" + url
                thread_urls.append(url)
                
        thread_urls = list(set(thread_urls))
        print(f"Found {len(thread_urls)} threads in the Google Group.")
        
        all_game_ids = set()
        
        # Open each thread and extract Poker Now game links
        for idx, t_url in enumerate(thread_urls):
            print(f"[{idx+1}/{len(thread_urls)}] Scraping thread: {t_url}")
            try:
                page.goto(t_url)
                # Wait for content to load
                page.wait_for_timeout(3500)
                body_text = page.locator("body").inner_text()
                game_ids = extract_game_ids(body_text)
                for gid in game_ids:
                    all_game_ids.add(gid)
            except Exception as e:
                print(f"Error scraping thread {t_url}: {e}")
                
        context.close()
        
    print(f"\nExtracted {len(all_game_ids)} total Poker Now game links from Google Groups.")
    


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
