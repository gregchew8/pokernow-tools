#!/usr/bin/env python3
import os
import sys
import json
import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

CREDENTIALS_FILE = "calendar_credentials.json"
ENV_VAR_CALENDAR = "CALENDAR_ID"

def load_env():
    env_file = os.path.join(os.path.dirname(__file__), ".env")
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
    calendar_id = os.environ.get(ENV_VAR_CALENDAR)
    
    if not calendar_id:
        print("Calendar sync skipped: CALENDAR_ID not set in environment.")
        sys.exit(0)

    if not os.path.exists(CREDENTIALS_FILE):
        print(f"Calendar sync skipped: '{CREDENTIALS_FILE}' credentials file not found.")
        print("Please follow the setup guide to create a Google Cloud Service Account and download the credentials key.")
        sys.exit(0)

    # Load the created game details
    if not os.path.exists("last_created_games.json"):
        print("Calendar sync skipped: last_created_games.json not found.")
        sys.exit(0)

    with open("last_created_games.json", "r") as f:
        game_history = json.load(f)

    date_str = game_history.get("date", "")
    tables = game_history.get("tables", [])
    
    if not tables:
        print("Calendar sync skipped: No tables found in game history.")
        sys.exit(0)

    # Format the description content
    desc_lines = ["Tonight's Poker Tables:", ""]
    primary_url = ""
    for t in tables:
        game_type = t.get("game_type", "").upper()
        table_num = t.get("table_num", 1)
        game_id = t.get("game_id", "")
        url = f"https://www.pokernow.club/games/{game_id}"
        if not primary_url:
            primary_url = url
        desc_lines.append(f"• {game_type} Table {table_num}: {url}")
    desc_lines.append("")
    desc_lines.append("Good luck at the tables!")
    description_text = "\n".join(desc_lines)

    # Setup Google Calendar Service
    print("Connecting to Google Calendar API...")
    try:
        scopes = ['https://www.googleapis.com/auth/calendar']
        creds = service_account.Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
        service = build('calendar', 'v3', credentials=creds)
    except Exception as e:
        print(f"Error authenticating with Google Calendar: {e}")
        sys.exit(1)

    # We want to check for events starting today.
    # Parse today's date (YYYY-MM-DD)
    try:
        y, m, d = map(int, date_str.split('-'))
        today = datetime.date(y, m, d)
    except Exception:
        today = datetime.date.today()

    # Time boundaries in Los Angeles timezone (or UTC offset)
    # We look between 5:00 PM and 11:59 PM local time today to find game night events
    # To keep timezone calculations dependency-free, let's use the local timezone offset of -07:00 (PST/PDT)
    time_min = f"{today}T17:00:00-07:00"
    time_max = f"{today}T23:59:59-07:00"

    print(f"Searching for existing events between {time_min} and {time_max}...")
    try:
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])
    except Exception as e:
        print(f"Error fetching events from calendar: {e}")
        print("Verify that you have shared your Google Calendar with the service account email.")
        sys.exit(1)

    event_id = None
    if events:
        # Match any event containing "poker" or "game" in title (case insensitive)
        for e in events:
            summary = e.get('summary', '').lower()
            if "poker" in summary or "game" in summary or "cash" in summary:
                event_id = e['id']
                print(f"Found matching event: '{e.get('summary')}' (ID: {event_id})")
                break

    # Format event subject
    today_dt = datetime.datetime(y, m, d)
    day = today_dt.day
    month_abbr = today_dt.strftime("%b")
    suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    event_summary = f"Cash Game Tonight ({month_abbr} {day}{suffix}, 7PM)"

    # Event payload details
    event_body = {
        'summary': event_summary,
        'description': description_text,
        'location': primary_url,
    }

    try:
        if event_id:
            # Update the existing event
            print(f"Updating event: {event_summary}")
            updated_event = service.events().patch(
                calendarId=calendar_id,
                eventId=event_id,
                body=event_body
            ).execute()
            print(f"Successfully updated calendar event: {updated_event.get('htmlLink')}")
        else:
            # Create a new event at 7:00 PM PST
            start_time = f"{today}T19:00:00-07:00"
            end_time = f"{today}T23:59:00-07:00"
            
            event_body.update({
                'start': {
                    'dateTime': start_time,
                    'timeZone': 'America/Los_Angeles',
                },
                'end': {
                    'dateTime': end_time,
                    'timeZone': 'America/Los_Angeles',
                }
            })
            print(f"No existing event found. Creating new event: {event_summary}")
            new_event = service.events().insert(
                calendarId=calendar_id,
                body=event_body
            ).execute()
            print(f"Successfully created calendar event: {new_event.get('htmlLink')}")
    except Exception as e:
        print(f"Error writing to Google Calendar event: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
