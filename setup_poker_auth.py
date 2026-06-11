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
from playwright.sync_api import Playwright, sync_playwright, expect


def copy_to_clipboard(html: str, text: str) -> None:
    # Convert html and text to hex bytes to avoid AppleScript escaping issues with quotation marks or newlines
    html_hex = html.encode('utf-8').hex()
    text_hex = text.encode('utf-8').hex()
    
    # AppleScript to set both HTML data (for email/rich text) and plain text (for terminals/chat)
    applescript = f'''
    set the clipboard to {{«class HTML»:«data HTML{html_hex}», «class utf8»:«data utf8{text_hex}»}}
    '''
    subprocess.run(['osascript', '-e', applescript], check=True)


def run(playwright: Playwright, tables_to_create: list) -> None:
    # Use persistent context to load our saved login session
    context = playwright.chromium.launch_persistent_context(
        user_data_dir="./chrome-profile",
        headless=False,
        args=["--disable-blink-features=AutomationControlled"]
    )
    
    urls = []
    admin_tokens = []
    total_tables = len(tables_to_create)
    
    # Map user game type to Poker Now option values
    variant_map = {
        "nlh": "th",
        "plo": "omaha",
        "plo8": "plo8"
    }
    
    for idx, (game_type, table_num) in enumerate(tables_to_create):
        variant_value = variant_map[game_type]
        print(f"Creating {game_type.upper()} table {table_num} ({idx+1} of {total_tables})...")
        
        # Reuse the default open tab for the first table, open new tabs for others
        if idx == 0 and context.pages:
            page = context.pages[0]
        else:
            page = context.new_page()
            
        page.goto("https://www.pokernow.com/start-game")
        
        # Enter Nickname (avoid pressing Enter to prevent premature submit)
        page.get_by_role("textbox", name="Your Nickname").click()
        page.get_by_role("textbox", name="Your Nickname").fill("Rerun")
        page.get_by_role("button", name="Create Game").click()
        
        # Wait for the room to load
        page.wait_for_timeout(4000)
        
        # Options & Configurations
        page.get_by_role("button", name=" Options").click()
        page.get_by_role("button", name=" Game Configurations").click()
        page.get_by_role("button", name="Yes").nth(1).click()
        
        # Wait for configurations dialog, then select the Poker Variant
        page.wait_for_timeout(1000)
        page.select_option("select#poker-variant", variant_value)
        
        # SB and BB settings
        page.get_by_role("textbox", name="SB").dblclick()
        page.get_by_role("textbox", name="SB").fill("0.025")
        page.get_by_role("textbox", name="SB").press("Tab")
        page.get_by_role("textbox", name="BB").fill("0.050")
        
        page.get_by_role("button", name="Ask Players").click()
        page.get_by_role("button", name="Yes").nth(3).click()
        
        # Time settings
        page.get_by_role("textbox").nth(4).click()
        page.get_by_role("textbox").nth(4).fill("60")
        page.get_by_role("textbox").nth(4).press("Tab")
        page.get_by_role("textbox").nth(5).fill("6")
        
        # Choose/Update Game
        page.locator("div:nth-child(17) > .col.col-2 > .choose-buttons > button").first.click()
        page.get_by_role("button", name="Update Game").click()
        page.get_by_role("button", name="Ok").click()
        page.get_by_role("button", name="« Back").click()
        
        # Capture the game room URL
        game_url = page.url
        urls.append(game_url)
        
        # Capture the room creator cookie (npt) to transfer admin control
        cookies = context.cookies("https://www.pokernow.com")
        npt_cookie = next((c["value"] for c in cookies if c["name"] == "npt"), None)
        admin_tokens.append(npt_cookie)
        
        page.close()
        
    context.close()
    
    # Format the plain text representation
    today = datetime.datetime.now()
    day_str = today.strftime("%d").lstrip('0')
    subject_line = f"Cash game tonight, ({today.strftime('%B')} {day_str}, 7pm)"
    
    formatted_lines = [f"Subject: {subject_line}", ""]
    html_links = [f"<b>Subject: {subject_line}</b>", ""]
    for idx, ((game_type, table_num), url) in enumerate(zip(tables_to_create, urls), 1):
        prefix = game_type.upper()
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
        "game_ids": [url.split("/games/")[-1] for url in urls],
        "tables": [{"game_type": t[0], "table_num": idx, "game_id": url.split("/games/")[-1]} for idx, (t, url) in enumerate(zip(tables_to_create, urls), 1)]
    }
    try:
        with open("last_created_games.json", "w") as f:
            json.dump(game_history, f, indent=4)
        print("Saved game details to 'last_created_games.json' for settlement automation.")
    except Exception as e:
        print(f"Warning: Could not save last_created_games.json: {e}")
        
    # Print Console Commands & Tokens to claim admin ownership on any other browser
    print("\n" + "="*60)
    print(" HOW TO CLAIM OWNER/ADMIN PRIVILEGES IN YOUR NORMAL BROWSER:")
    print("="*60)
    print(" Option A (EASIEST): Click your 'Claim Poker Admin' Bookmarklet")
    print("            and paste the clean Token when prompted.")
    print(" Option B:  Paste the console Command in DevTools (F12) Console.")
    print("="*60)
    for idx, ((game_type, table_num), url, token) in enumerate(zip(tables_to_create, urls, admin_tokens), 1):
        if token:
            print(f" Table {idx} ({game_type.upper()} Table {idx}):")
            print(f"   Token:   {token}")
            print(f"   Command: document.cookie=\"npt={token}; path=/; domain=.pokernow.com\"; location.reload();\n")
    print("="*60 + "\n")


if __name__ == "__main__":
    tables_to_create = []
    allowed_types = ["nlh", "plo", "plo8"]
    
    args = sys.argv[1:]
    if len(args) == 0:
        # Default: create 1 NLH table
        tables_to_create.append(("nlh", 1))
    else:
        # Check if the first argument is just a single number (e.g. python3 setup_poker_auth.py 3)
        if len(args) == 1 and args[0].isdigit():
            num = int(args[0])
            for idx in range(num):
                tables_to_create.append(("nlh", idx + 1))
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
                        tables_to_create.append((arg, current_type_count + 1))
                else:
                    print(f"Error: Unknown argument '{arg}'")
                    print("Usage: python3 setup_poker_auth.py [nlh|plo|plo8] [count] [nlh|plo|plo8] [count] ...")
                    sys.exit(1)
                    
    with sync_playwright() as playwright:
        run(playwright, tables_to_create)
