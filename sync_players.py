#!/usr/bin/env python3
import os
import sys
import requests

CSV_FILE = "payment_info.csv"
ENV_VAR = "GOOGLE_SHEET_CSV_URL"

def main():
    url = os.environ.get(ENV_VAR)
    if not url:
        # Check if payment_info.csv already exists locally
        if os.path.exists(CSV_FILE):
            print(f"[{ENV_VAR}] env var not set. Using existing local '{CSV_FILE}'.")
            sys.exit(0)
        else:
            print(f"Error: [{ENV_VAR}] env var not set and local '{CSV_FILE}' does not exist.")
            print("Please set the GOOGLE_SHEET_CSV_URL environment variable containing the Google Sheet CSV export link.")
            sys.exit(1)

    print(f"Syncing player database from Google Sheet...")
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        
        # Ensure the content is not empty and resembles CSV headers
        content = response.text
        if "PN Alias" not in content and "Venmo" not in content and "," not in content:
            print("Warning: The downloaded content does not seem to be a valid CSV file.")
            
        with open(CSV_FILE, "w", encoding="utf-8") as f:
            f.write(content)
            
        print(f"Successfully updated '{CSV_FILE}' ({len(content)} bytes).")
    except Exception as e:
        print(f"Error downloading sheet: {e}")
        if os.path.exists(CSV_FILE):
            print("Falling back to existing local file.")
        else:
            sys.exit(1)

if __name__ == "__main__":
    main()
