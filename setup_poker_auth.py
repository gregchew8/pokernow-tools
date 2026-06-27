"""
Poker Now Room Setup Automation Script
======================================

This script automates the creation and configuration of private game rooms on Poker Now.
It automatically takes a seat, applies configurations (blinds, action timers, etc.),
and copies the resulting room URLs to the macOS clipboard in a ready-to-share format:
    PREFIX - Table X <URL>

Prerequisites:
--------------
1. Install Python 3.
2. Install Playwright for Python:
   $ pip install playwright
3. Install the Playwright Chromium browser:
   $ playwright install chromium

First-Time Setup (Authentication):
----------------------------------
To log into your Poker Now account (e.g. via Google), run the `login.py` script once:
   $ python3 login.py

This opens a headed browser window with anti-detection flags enabled. Log in to your
account, and once you are finished, press ENTER in the terminal to close the browser
and save your session details to the local `./chrome-profile` directory.

Usage:
------
Run the script specifying any combination of game variants and table counts:

   $ python3 setup_poker_auth.py [game_type] [count] [game_type] [count] ...

Arguments:
  [game_type]  The variant of poker to create: nlh, plo, plo8
  [count]      The number of tables of the preceding variant to create. (Default: 1)

Examples:
  - Create a combo of 2 NLH tables and 2 PLO tables in a single run:
    $ python3 setup_poker_auth.py nlh 2 plo 2

  - Create 3 PLO8 tables:
    $ python3 setup_poker_auth.py plo8 3

  - Create 1 PLO table and 1 PLO8 table:
    $ python3 setup_poker_auth.py plo plo8

  - Create 3 NLH tables (shortcut if no game type is specified):
    $ python3 setup_poker_auth.py 3
"""

import re
import sys
import json
import datetime
import subprocess
import os
import random

# Set custom Playwright browsers path to persist Chromium executable outside macOS Library cache sweeps
working_dir = os.path.dirname(os.path.abspath(__file__))
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(working_dir, "playwright-browsers")

from playwright.sync_api import Playwright, sync_playwright, expect


def copy_to_clipboard(html: str, text: str) -> None:
    try:
        # Convert html and text to hex bytes to avoid AppleScript escaping issues with quotation marks or newlines
        html_hex = html.encode('utf-8').hex()
        text_hex = text.encode('utf-8').hex()
        
        # AppleScript to set both HTML data (for email/rich text) and plain text (for terminals/chat)
        applescript = f'''
        set the clipboard to {{«class HTML»:«data HTML{html_hex}», «class utf8»:«data utf8{text_hex}»}}
        '''
        subprocess.run(['osascript', '-e', applescript], check=True)
    except Exception as e:
        print(f"Warning: Could not copy to clipboard (this is expected on non-macOS/CI environments): {e}")



def sync_cookies_from_main_profile(target_user_data_dir: str):
    import shutil
    import glob
    
    chrome_base = os.path.expanduser("~/Library/Application Support/Google/Chrome")
    profile_dirs = glob.glob(os.path.join(chrome_base, "Default")) + glob.glob(os.path.join(chrome_base, "Profile *"))
    
    # Sort profile directories by mtime of their Cookies file or the directory itself
    def get_mtime(d):
        cookies_path = os.path.join(d, "Cookies")
        if os.path.exists(cookies_path):
            return os.path.getmtime(cookies_path)
        return os.path.getmtime(d)
        
    profile_dirs.sort(key=get_mtime, reverse=True)
    if not profile_dirs:
        print("Warning: Could not find any Chrome profiles to sync.")
        return
        
    src_base = profile_dirs[0]
    print(f"Detected active Chrome profile: {os.path.basename(src_base)}")
    
    dest_base = os.path.join(target_user_data_dir, "Default")
    os.makedirs(dest_base, exist_ok=True)
    
    # Copy Cookies
    src_cookies = os.path.join(src_base, "Cookies")
    dest_cookies = os.path.join(dest_base, "Cookies")
    if os.path.exists(src_cookies):
        try:
            shutil.copy2(src_cookies, dest_cookies)
            print("Successfully synced Cookies database.")
        except Exception as e:
            print(f"Warning: Could not sync Cookies database: {e}")
            
    # Copy Local Storage
    src_ls = os.path.join(src_base, "Local Storage")
    dest_ls = os.path.join(dest_base, "Local Storage")
    if os.path.exists(src_ls):
        try:
            if os.path.exists(dest_ls):
                shutil.rmtree(dest_ls)
            shutil.copytree(src_ls, dest_ls)
            print("Successfully synced Local Storage.")
        except Exception as e:
            print(f"Warning: Could not sync Local Storage: {e}")


def open_new_chrome_tab(port: int, url: str):
    import urllib.request
    import urllib.parse
    try:
        encoded_url = urllib.parse.quote(url, safe='')
        endpoint = f"http://localhost:{port}/json/new?{encoded_url}"
        req = urllib.request.Request(endpoint, method='PUT')
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status == 200
    except Exception as e:
        print(f"Error opening new Chrome tab: {e}")
        return False


def run(playwright: Playwright, tables_to_create: list, headless: bool = False) -> None:
    import urllib.request
    import time
    
    user_data_dir = os.path.abspath("./chrome-profile")
    port = 9228
    
    # Clean up any leftover Chrome profiles
    subprocess.run(["pkill", "-f", "chrome-profile"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    
    # Sync cookies and session from the user's main Google Chrome profile to local profile
    sync_cookies_from_main_profile(user_data_dir)
    
    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    # Launch Chrome directly with the target URL as the first argument to avoid immediate CDP detection on load
    cmd = [
        chrome_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "https://www.pokernow.com/start-game"
    ]
    if headless:
        cmd.append("--headless=new")
        
    print(f"Launching Chrome via subprocess: {' '.join(cmd)}")
    chrome_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Wait for the debugging port to open
    connected = False
    for _ in range(50):
        try:
            with urllib.request.urlopen(f"http://localhost:{port}/json/version", timeout=1) as response:
                if response.status == 200:
                    connected = True
                    break
        except Exception:
            pass
        time.sleep(0.1)
        
    if not connected:
        raise RuntimeError("Failed to launch Google Chrome with remote debugging port.")
    print("Chrome successfully launched. Deferring Playwright connection until first table is created...")
    
    urls = []
    admin_tokens = []
    total_tables = len(tables_to_create)
    
    # Map user game type to Poker Now option values
    variant_map = {
        "nlh": "th",
        "plo": "omaha",
        "plo8": "plo8"
    }
    
    browser = None
    context = None
    configured_game_ids = set()
    
    for idx, table_info in enumerate(tables_to_create):
        # Support both 2-tuples and 4-tuples for backward compatibility
        if len(table_info) == 4:
            game_type, table_num, sb, bb = table_info
        else:
            game_type, table_num = table_info
            sb, bb = "0.25", "0.50"
            
        variant_value = variant_map[game_type]
        print(f"\n============================================================")
        print(f" TABLE {idx+1} of {total_tables}: {game_type.upper()} ({sb}/{bb})")
        print(f"============================================================")
        
        # 1. Open the start-game page if it is not the first table (which was opened on launch)
        if idx > 0:
            print("Opening new tab for next table...")
            open_new_chrome_tab(port, "https://www.pokernow.com/start-game")
            time.sleep(2)
            
        # 2. Instruct the user to solve Turnstile and click Create Game
        import json
        print("\n" + "="*60)
        print(f" ACTION REQUIRED FOR TABLE {idx+1}:")
        print(" 1. In the Chrome window, click the Turnstile checkbox ('Verify you are human').")
        print(" 2. Enter a Nickname (e.g. 'Rerun') and click 'Create Game'.")
        print(" The script will automatically detect the game, connect, and configure it!")
        print("="*60 + "\n")
        
        # 3. Poll http://localhost:9228/json to detect the newly created game
        detected_url = None
        detected_game_id = None
        for _ in range(300): # 5 minutes
            try:
                with urllib.request.urlopen(f"http://localhost:{port}/json", timeout=2) as response:
                    if response.status == 200:
                        tabs = json.loads(response.read().decode("utf-8"))
                        for tab in tabs:
                            tab_url = tab.get("url", "")
                            if "/games/pgl" in tab_url:
                                # Extract game ID
                                game_id = tab_url.split("/games/")[1].split("?")[0]
                                if game_id not in configured_game_ids:
                                    detected_url = tab_url
                                    detected_game_id = game_id
                                    break
            except Exception:
                pass
            if detected_url:
                break
            time.sleep(1)
            
        if not detected_url:
            raise RuntimeError(f"Timed out waiting for manual game creation on Table {idx+1}.")
            
        print(f"Detected game room: {detected_url}. Connecting Playwright to configure settings...")
        
        # 4. Connect Playwright
        browser = playwright.chromium.connect_over_cdp(f"http://localhost:{port}")
        context = browser.contexts[0]
        context.add_init_script("delete navigator.__proto__.webdriver;")
        
        # 5. Find the page matching the detected game ID
        page = None
        for p in context.pages:
            if detected_game_id in p.url:
                page = p
                break
        if not page:
            page = context.pages[0]
            
        # 6. Configure the game settings
        page.wait_for_timeout(2000)
        
        # Options & Configurations (use exact=False to avoid icon rendering/matching issues in CI)
        options_btn = page.get_by_role("button", name="Options", exact=False)
        options_btn.hover()
        page.wait_for_timeout(random.randint(300, 700))
        options_btn.click()
        page.wait_for_timeout(random.randint(500, 1200))
        
        configs_btn = page.get_by_role("button", name="Game Configurations", exact=False)
        configs_btn.hover()
        page.wait_for_timeout(random.randint(300, 700))
        configs_btn.click()
        page.wait_for_timeout(random.randint(1000, 2000)) # Wait for configs popup
        
        yes_btn = page.get_by_role("button", name="Yes").nth(1)
        yes_btn.hover()
        page.wait_for_timeout(random.randint(200, 500))
        yes_btn.click()
        
        # Wait for configurations dialog, then select the Poker Variant
        page.wait_for_timeout(random.randint(1000, 2000))
        page.select_option("select#poker-variant", variant_value)
        page.wait_for_timeout(random.randint(500, 1200))
        
        # SB and BB settings
        sb_field = page.get_by_role("textbox", name="SB")
        sb_field.hover()
        page.wait_for_timeout(random.randint(200, 500))
        sb_field.fill(sb)
        page.wait_for_timeout(random.randint(400, 800))
        
        bb_field = page.get_by_role("textbox", name="BB")
        bb_field.hover()
        page.wait_for_timeout(random.randint(200, 500))
        bb_field.fill(bb)
        page.wait_for_timeout(random.randint(600, 1500))
        
        ask_players_btn = page.get_by_role("button", name="Ask Players")
        ask_players_btn.hover()
        page.wait_for_timeout(random.randint(300, 700))
        ask_players_btn.click()
        page.wait_for_timeout(random.randint(1000, 2000))
        
        yes_nth_btn = page.get_by_role("button", name="Yes").nth(3)
        yes_nth_btn.hover()
        page.wait_for_timeout(random.randint(200, 500))
        yes_nth_btn.click()
        page.wait_for_timeout(random.randint(500, 1200))
        
        # Time settings
        timer1_field = page.get_by_role("textbox").nth(4)
        timer1_field.hover()
        page.wait_for_timeout(random.randint(200, 500))
        timer1_field.fill("60")
        page.wait_for_timeout(random.randint(300, 700))
        
        timer2_field = page.get_by_role("textbox").nth(5)
        timer2_field.hover()
        page.wait_for_timeout(random.randint(200, 500))
        timer2_field.fill("6")
        page.wait_for_timeout(random.randint(600, 1500))
        
        # Showdown Presentation Time to FAST (3S)
        fast_btn = page.get_by_role("button", name="FAST (3S)", exact=False)
        fast_btn.hover()
        page.wait_for_timeout(random.randint(300, 700))
        fast_btn.click()
        page.wait_for_timeout(random.randint(500, 1200))
        
        update_btn = page.get_by_role("button", name="Update Game")
        update_btn.hover()
        page.wait_for_timeout(random.randint(300, 700))
        update_btn.click()
        page.wait_for_timeout(random.randint(1000, 2000))
        
        ok_btn = page.get_by_role("button", name="Ok")
        ok_btn.hover()
        page.wait_for_timeout(random.randint(200, 500))
        ok_btn.click()
        page.wait_for_timeout(random.randint(500, 1200))
        
        back_btn = page.get_by_role("button", name="« Back")
        back_btn.hover()
        page.wait_for_timeout(random.randint(300, 700))
        back_btn.click()
        page.wait_for_timeout(random.randint(1000, 2000))
        
        # Capture the game room URL
        game_url = page.url
        urls.append(game_url)
        
        # Capture the room creator cookie (npt) to transfer admin control
        cookies = context.cookies("https://www.pokernow.com")
        npt_cookie = next((c["value"] for c in cookies if c["name"] == "npt"), None)
        admin_tokens.append(npt_cookie)
        
        # Extract game ID directly from game_url
        game_id = game_url.split("/games/")[-1].split("?")[0]
        configured_game_ids.add(game_id)
        print(f"Table {idx+1} successfully configured!")
        
        context.close()
        browser.close()
        print("Playwright disconnected. Chrome is now clean for the next table.")
        
    chrome_process.terminate()
    chrome_process.wait()
    
    # Format the plain text representation
    today = datetime.datetime.now()
    day = today.day
    month_abbr = today.strftime("%b")
    suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    subject_line = f"Cash Game Tonight ({month_abbr} {day}{suffix}, 7PM)"
    
    formatted_lines = [f"Subject: {subject_line}", ""]
    html_links = [f"<b>Subject: {subject_line}</b>", ""]
    for idx, (t, url) in enumerate(zip(tables_to_create, urls), 1):
        game_type = t[0]
        sb = t[2] if len(t) == 4 else "0.25"
        bb = t[3] if len(t) == 4 else "0.50"
        stakes = f" {sb}/{bb}"
        prefix = f"{game_type.upper()}{stakes}"
        formatted_lines.append(f"{prefix} - Table {idx} <{url}>")
        html_links.append(f'<a href="{url}">{prefix} - Table {idx}</a>')
        
    all_output_text = "\n".join(formatted_lines)
    all_html_links = "<br>".join(html_links)
    
    # Print results to the terminal
    print("\n" + "="*60)
    print(f" SUCCESS: CREATED {total_tables} POKER TABLE(S)")
    print("="*60)
    for line in formatted_lines:
        print(line)
    print("="*60 + "\n")
    
    # Copy both rich text HTML and plain text to the clipboard
    copy_to_clipboard(all_html_links, all_output_text)
    print("All formatted URLs have been copied to your clipboard (both plain text and clickable email links)!")
    
    # Save the created game details to a JSON file for the settlement script
    today = datetime.datetime.now()
    game_history = {
        "date": today.strftime("%Y-%m-%d"),
        "description": today.strftime("%m%d%y"),
        "is_adhoc": is_adhoc,
        "game_ids": [url.split("/games/")[-1] for url in urls],
        "tables": [{"game_type": t[0], "table_num": idx, "game_id": url.split("/games/")[-1], "sb": t[2] if len(t) == 4 else "0.25", "bb": t[3] if len(t) == 4 else "0.50"} for idx, (t, url) in enumerate(zip(tables_to_create, urls), 1)]
    }
    import time
    import errno
    for attempt in range(10):
        try:
            with open("last_created_games.json", "w") as f:
                json.dump(game_history, f, indent=4)
            print("Saved game details to 'last_created_games.json' for settlement automation.")
            break
        except OSError as e:
            if e.errno in (errno.EDEADLK, errno.EAGAIN) and attempt < 9:
                print(f"Google Drive sync lock detected, retrying write to last_created_games.json ({attempt + 1}/10)...")
                time.sleep(1.0)
            else:
                print(f"Warning: Could not save last_created_games.json: {e}")
                break
        
    # Print Console Commands & Tokens to claim admin ownership on any other browser
    print("\n" + "="*60)
    print(" HOW TO CLAIM OWNER/ADMIN PRIVILEGES IN YOUR NORMAL BROWSER:")
    print("="*60)
    print(" Option A (EASIEST): Click your 'Claim Poker Admin' Bookmarklet")
    print("            and paste the clean Token when prompted.")
    print(" Option B:  Paste the console Command in DevTools (F12) Console.")
    print("="*60)
    for idx, (t, url, token) in enumerate(zip(tables_to_create, urls, admin_tokens), 1):
        game_type = t[0]
        if token:
            print(f" Table {idx} ({game_type.upper()} Table {idx}):")
            print(f"   Token:   {token}")
            print(f"   Command: document.cookie=\"npt={token}; path=/; domain=.pokernow.com\"; location.reload();\n")
    print("="*60 + "\n")


if __name__ == "__main__":
    tables_to_create = []
    allowed_types = ["nlh", "plo", "plo8"]
    
    args = sys.argv[1:]
    
    # Check for adhoc flag
    is_adhoc = False
    if "--adhoc" in args:
        is_adhoc = True
        args.remove("--adhoc")
        
    # Check for headless flag
    headless = False
    if "--headless" in args:
        headless = True
        args.remove("--headless")
        
    # Check for JSON config flag
    if "--config" in args:
        idx = args.index("--config")
        config_str = args[idx + 1]
        args.pop(idx + 1)
        args.pop(idx)
        
        try:
            config_data = json.loads(config_str)
            for idx, t in enumerate(config_data, 1):
                gtype = t.get("type", "nlh").lower()
                if gtype == "pl8":
                    gtype = "plo8"
                if gtype not in allowed_types:
                    gtype = "nlh"
                current_type_count = len([x for x in tables_to_create if x[0] == gtype])
                tables_to_create.append((gtype, current_type_count + 1, t.get("sb", "0.25"), t.get("bb", "0.50")))
        except Exception as e:
            print(f"Error parsing --config JSON: {e}")
            sys.exit(1)
    else:
        # Check for custom SB/BB flags for backward compatibility/quick overrides
        sb = "0.25"
        bb = "0.50"
        if "--sb" in args:
            idx = args.index("--sb")
            if idx + 1 < len(args):
                sb = args[idx + 1]
                args.pop(idx + 1)
            args.pop(idx)
            
        if "--bb" in args:
            idx = args.index("--bb")
            if idx + 1 < len(args):
                bb = args[idx + 1]
                args.pop(idx + 1)
            args.pop(idx)
            
        if len(args) == 0:
            # Default: create 1 NLH table
            tables_to_create.append(("nlh", 1, sb, bb))
        else:
            # Check if the first argument is just a single number (e.g. python3 setup_poker_auth.py 3)
            if len(args) == 1 and args[0].isdigit():
                num = int(args[0])
                for idx in range(num):
                    tables_to_create.append(("nlh", idx + 1, sb, bb))
            else:
                # Parse pairs: [game_type] [count] [game_type] [count] ...
                i = 0
                while i < len(args):
                    arg = args[i].lower()
                    if arg in allowed_types:
                        count = 1
                        # Check if next argument is a count
                        if i + 1 < len(args) and args[i+1].isdigit():
                            count = int(args[i+1])
                            i += 2
                        else:
                            i += 1
                        
                        for _ in range(count):
                            current_type_count = len([t for t in tables_to_create if t[0] == arg])
                            tables_to_create.append((arg, current_type_count + 1, sb, bb))
                    else:
                        print(f"Error: Unknown argument '{arg}'")
                        print("Usage: python3 setup_poker_auth.py [--headless] [--config JSON_STRING] [--sb SB] [--bb BB] [nlh|plo|plo8] [count] [nlh|plo|plo8] [count] ...")
                        sys.exit(1)
                        
    with sync_playwright() as playwright:
        run(playwright, tables_to_create, headless=headless)
