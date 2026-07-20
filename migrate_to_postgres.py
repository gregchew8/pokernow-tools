#!/usr/bin/env python3
import sys
import os
import sqlite3

sys.path.append("/Users/gregchew/pokernow")

from db_client import DBClient

def load_env():
    working_dir = "/Users/gregchew/pokernow"
    env_file = os.path.join(working_dir, ".env")
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        key, val = line.split("=", 1)
                        os.environ[key.strip()] = val.strip().strip('"').strip("'")

def migrate():
    load_env()
    sqlite_db_path = "/Users/gregchew/Library/CloudStorage/GoogleDrive-gregchew@gmail.com/My Drive/pokernow/data/poker_stats.db"


    if not os.path.exists(sqlite_db_path):
        print(f"[Migration] Local SQLite database not found at {sqlite_db_path}. Nothing to migrate.")
        return

    print("[Migration] Connecting to local SQLite database...")
    lite_conn = sqlite3.connect(sqlite_db_path)
    lite_conn.row_factory = sqlite3.Row
    lite_cursor = lite_conn.cursor()

    print("[Migration] Connecting to Railway PostgreSQL database...")
    # This automatically reads DATABASE_URL from .env or environment
    db = DBClient()
    if not db.is_postgres:
        print("[ERROR] DBClient did not detect PostgreSQL environment! Check DATABASE_URL in .env.")
        sys.exit(1)

    print("[Migration] Fetching sessions from SQLite...")
    lite_cursor.execute("SELECT ledger_date, filename FROM sessions")
    sessions = lite_cursor.fetchall()
    print(f"[Migration] Found {len(sessions)} sessions.")

    print("[Migration] Inserting sessions into Postgres...")
    for row in sessions:
        db.execute(
            "INSERT INTO sessions (ledger_date, filename) VALUES (?, ?) ON CONFLICT (ledger_date) DO NOTHING",
            (row["ledger_date"], row["filename"])
        )
    db.commit()

    print("[Migration] Fetching ledger records from SQLite...")
    lite_cursor.execute("SELECT player_nickname, player_id, session_start_at, session_end_at, buy_in, buy_out, net, ledger_date FROM player_ledger_records")
    records = lite_cursor.fetchall()
    print(f"[Migration] Found {len(records)} player records.")

    print("[Migration] Inserting player records into Postgres...")
    db.execute("DELETE FROM player_ledger_records")
    
    for row in records:
        db.execute(
            "INSERT INTO player_ledger_records (player_nickname, player_id, session_start_at, session_end_at, buy_in, buy_out, net, ledger_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (row["player_nickname"], row["player_id"], row["session_start_at"], row["session_end_at"], row["buy_in"], row["buy_out"], row["net"], row["ledger_date"])
        )
    db.commit()

    print("[Migration] Verifying Postgres counts...")
    c_sessions = db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    c_records = db.execute("SELECT COUNT(*) FROM player_ledger_records").fetchone()[0]
    print(f"[Migration] Verification: {c_sessions} sessions and {c_records} player records successfully written to Postgres!")

    lite_conn.close()

if __name__ == "__main__":
    migrate()
