#!/usr/bin/env python3
"""
batch_stage_games.py
Orchestrates staging tables for upcoming days in a single session.
"""

import os
import sys
import json
import time
import datetime
import subprocess
import stage_manager

WORKING_DIR = os.path.dirname(os.path.abspath(__file__))

def get_upcoming_scheduled_days(count=3, start_date=None):
    """
    Finds the next `count` game days based on schedule.json.
    Returns list of dicts: [{'date': 'YYYY-MM-DD', 'day': 'friday', 'tables': [...]}, ...]
    """
    schedule_file = os.path.join(WORKING_DIR, "schedule.json")
    if not os.path.exists(schedule_file):
        print("Error: schedule.json not found.", file=sys.stderr)
        return []

    with open(schedule_file, "r") as f:
        schedule = json.load(f)

    if start_date is None:
        start_date = datetime.date.today()

    upcoming = []
    curr = start_date
    # Look ahead up to 14 days
    for _ in range(14):
        # We look starting from tomorrow if today's setup has already passed, or from today
        day_name = curr.strftime("%A").lower()
        if day_name in schedule:
            tables = schedule[day_name].get("tables", [])
            if tables:
                upcoming.append({
                    "date": curr.strftime("%Y-%m-%d"),
                    "day": day_name,
                    "tables": tables
                })
                if len(upcoming) >= count:
                    break
        curr += datetime.timedelta(days=1)

    return upcoming

def stage_batch(days_count=None, target_dates=None, is_adhoc=False):
    """
    Stages tables for the requested days sequentially.
    """
    days_to_stage = []

    if target_dates:
        schedule_file = os.path.join(WORKING_DIR, "schedule.json")
        schedule = {}
        if os.path.exists(schedule_file):
            with open(schedule_file, "r") as f:
                schedule = json.load(f)
        for d_str in target_dates:
            dt = datetime.datetime.strptime(d_str, "%Y-%m-%d").date()
            d_name = dt.strftime("%A").lower()
            tbls = schedule.get(d_name, {}).get("tables", [])
            if not tbls:
                tbls = [{"type": "nlh", "sb": "0.25", "bb": "0.50"}]
            days_to_stage.append({
                "date": d_str,
                "day": d_name,
                "tables": tbls
            })
    else:
        # Default: next count scheduled days starting tomorrow (or today if early)
        days_count = days_count or 2
        # Start looking from tomorrow by default so we don't accidentally stage past/today game
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        days_to_stage = get_upcoming_scheduled_days(count=days_count, start_date=tomorrow)

    if not days_to_stage:
        print("No scheduled game days found to stage.")
        return False

    total_days = len(days_to_stage)
    print(f"\n============================================================")
    print(f" BATCH STAGING: {total_days} UPCOMING GAME NIGHTS")
    for d in days_to_stage:
        print(f" - {d['date']} ({d['day'].capitalize()}): {len(d['tables'])} tables")
    print(f"============================================================\n")

    for d_idx, day_info in enumerate(days_to_stage, start=1):
        target_date_str = day_info["date"]
        target_day_name = day_info["day"]
        tables = day_info["tables"]
        config_str = json.dumps(tables)

        print(f"\n>>> Staging Day {d_idx} of {total_days}: {target_date_str} ({target_day_name.capitalize()}) <<<")

        cmd = [
            sys.executable,
            "setup_poker_auth.py",
            "--config", config_str,
            "--stage-date", target_date_str,
            "--stage-day-name", target_day_name
        ]
        if is_adhoc:
            cmd.append("--adhoc")

        res = subprocess.run(cmd)
        if res.returncode != 0:
            print(f"[BatchStaging] Error: setup_poker_auth.py failed on {target_date_str} with code {res.returncode}", file=sys.stderr)
            return False

        print(f">>> Day {d_idx} of {total_days} ({target_date_str}) successfully staged! <<<\n")
        time.sleep(3)

    print("\n============================================================")
    print(f" ALL {total_days} DAYS SUCCESSFULLY STAGED IN QUEUE!")
    print("============================================================\n")
    return True

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Batch stage upcoming poker games.")
    parser.add_argument("--days", type=int, default=2, help="Number of upcoming scheduled game nights to stage (default 2)")
    parser.add_argument("--dates", type=str, help="Comma-separated list of YYYY-MM-DD dates to stage")
    parser.add_argument("--date", type=str, help="Single YYYY-MM-DD date to stage")
    parser.add_argument("--config", type=str, help="Custom JSON config of tables for single date")
    args = parser.parse_args()

    if args.date:
        dates = [args.date.strip()]
        stage_batch(target_dates=dates)
    elif args.dates:
        dates = [d.strip() for d in args.dates.split(",") if d.strip()]
        stage_batch(target_dates=dates)
    else:
        stage_batch(days_count=args.days)
