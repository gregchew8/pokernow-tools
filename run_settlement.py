#!/usr/bin/env python3
import os
import sys
import re
import csv
import subprocess
import datetime

CSV_FILE = "payment_info.csv"
SETTLEMENT_SCRIPT = "pokernow_settlement.py"


def extract_game_ids(text):
    # Regex to find Poker Now game URLs or raw game IDs starting with pgl
    # Matches URLs like: https://www.pokernow.com/games/pgl-mgKJqngvVeQrKLOpq7C1t
    url_pattern = r'pokernow\.(?:com|club)/games/(pgl[a-zA-Z0-9_-]+)'
    raw_pattern = r'\b(pgl[a-zA-Z0-9_-]{10,})\b'
    
    # Try URLs first
    ids = re.findall(url_pattern, text)
    if not ids:
        # Fallback to finding raw pgl IDs in text
        ids = re.findall(raw_pattern, text)
        
    # Remove duplicates preserving order
    seen = set()
    return [x for x in ids if not (x in seen or seen.add(x))]


def prompt_game_ids():
    print("\nPlease paste the game links, email text, or game IDs.")
    print("Press Enter twice (or type 'done' on a new line) when finished:")
    
    lines = []
    while True:
        try:
            line = input()
            if line.strip().lower() == 'done':
                break
            # If the user presses enter twice on empty lines, finish input
            if not line.strip() and lines and not lines[-1].strip():
                break
            lines.append(line)
        except KeyboardInterrupt:
            print("\nAborted.")
            sys.exit(0)
            
    pasted_text = "\n".join(lines)
    game_ids = extract_game_ids(pasted_text)
    
    if not game_ids:
        print("\nError: No valid game IDs (starting with 'pgl') could be found in the pasted text.")
        return prompt_game_ids()
        
    print(f"\nFound {len(game_ids)} game ID(s):")
    for idx, gid in enumerate(game_ids, 1):
        print(f"  {idx}. {gid}")
        
    confirm = input("Confirm these game IDs? (Y/n): ").strip().lower()
    if confirm in ('n', 'no'):
        return prompt_game_ids()
        
    return game_ids


def main():
    print("="*60)
    print(" POKER NOW SETTLEMENT AUTOMATION")
    print("="*60)

    # 1. Determine default description (yesterday's date)
    yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
    default_desc = yesterday.strftime("%m%d%y")

    # Prompt for Description first
    desc_input = input(f"Enter description/date note for payments [default: {default_desc}]: ").strip()
    description = desc_input if desc_input else default_desc

    # 2. Prompt for game links/IDs and extract them
    game_ids = prompt_game_ids()

    # 3. Human in the loop check to verify games are over
    print("\n" + "="*50)
    print(" HUMAN IN THE LOOP VERIFICATION")
    print("="*50)
    print("Please verify that there are no active hands/players at the tables.")
    while True:
        confirm = input("Are all games finished and ready for settlement? (Y/n): ").strip().lower()
        if not confirm or confirm in ('y', 'yes'):
            break
        elif confirm in ('n', 'no'):
            print("Settlement cancelled. Please finish games before running this script.")
            sys.exit(0)
        else:
            print("Please enter 'y' or 'n' (or press Enter for yes).")

    # 4. Run loop with interactive error mapping correction
    while True:
        print(f"\nRunning settlement script: python3 {SETTLEMENT_SCRIPT} --description {description} --game_ids {' '.join(game_ids)}")
        
        # Build command
        cmd = [
            sys.executable,
            SETTLEMENT_SCRIPT,
            "--description", description,
            "--game_ids"
        ] + game_ids
        
        # Run and capture output
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Capture full output to parse for nickname errors
        full_output = []
        
        # Stream stdout in real time so the user sees progress
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                print(line, end="")
                full_output.append(line)
                
        # Read remaining stderr
        stderr_output = process.stderr.read()
        if stderr_output:
            print(stderr_output, end="")
            full_output.append(stderr_output)
            
        return_code = process.wait()
        
        if return_code == 0:
            print("\n============================================================")
            print(" SUCCESS: Settlement generated successfully!")
            print("============================================================")
            break
        
        # Check if the failure is due to a missing player nickname in the payment info
        full_text = "".join(full_output)
        match = re.search(r"Error: Player with nickname '([^']+)' not found in Payment mapping", full_text)
        
        if match:
            missing_nick = match.group(1)
            print(f"\nFound missing nickname: '{missing_nick}'")
            print("We need to add this player's Venmo / payment handle to continue.")
            
            while True:
                handle = input(f"Enter payment handle for '{missing_nick}' (e.g., @username or phone/link): ").strip()
                if handle:
                    if not handle.startswith('@') and not handle.startswith('http') and '/' not in handle and '-' not in handle:
                        if not any(c in handle for c in ['@', '+']):
                            handle = '@' + handle
                    break
                print("Payment handle cannot be empty. Type Ctrl+C to abort.")
                
            # Safely append to payment_info.csv
            try:
                # First check if file has trailing newline
                needs_newline = False
                if os.path.exists(CSV_FILE):
                    with open(CSV_FILE, 'rb') as f:
                        f.seek(0, 2)
                        if f.tell() > 0:
                            f.seek(-1, 2)
                            last_char = f.read(1)
                            if last_char != b'\n' and last_char != b'\r':
                                needs_newline = True
                
                with open(CSV_FILE, 'a', encoding='utf-8') as f:
                    if needs_newline:
                        f.write("\n")
                    f.write(f"{missing_nick},{missing_nick},{handle},{handle}\n")
                print(f"Added '{missing_nick}' with handle '{handle}' to {CSV_FILE}.")
                print("Retrying settlement...")
                continue
            except Exception as e:
                print(f"Error appending to {CSV_FILE}: {e}")
                sys.exit(1)
        else:
            print(f"\nSettlement script failed with exit code {return_code}. Exiting.")
            sys.exit(return_code)


if __name__ == "__main__":
    main()
