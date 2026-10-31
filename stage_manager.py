#!/usr/bin/env python3
"""
stage_manager.py
Manages multi-day game staging, health verification, and queue operations for Poker Now automation.
"""

import os
import sys
import json
import time
import datetime
import urllib.request
import urllib.error
import ssl

def get_ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        try:
            return ssl._create_unverified_context()
        except Exception:
            return None

WORKING_DIR = os.path.dirname(os.path.abspath(__file__))
STAGED_GAMES_FILE = os.path.join(WORKING_DIR, "output", "staged_games.json")

# Health check constants
MAX_STAGING_AGE_HOURS = 120  # 5 days = 120 hours
HTTP_TIMEOUT_SECONDS = 10

def load_staged_games():
    """Loads all staged games from disk."""
    if not os.path.exists(STAGED_GAMES_FILE):
        return {}
    try:
        with open(STAGED_GAMES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[StageManager] Error loading {STAGED_GAMES_FILE}: {e}", file=sys.stderr)
        return {}

def save_staged_games(data):
    """Atomically writes staged games to disk."""
    try:
        os.makedirs(os.path.dirname(STAGED_GAMES_FILE), exist_ok=True)
        temp_file = STAGED_GAMES_FILE + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        os.replace(temp_file, STAGED_GAMES_FILE)
        return True
    except Exception as e:
        print(f"[StageManager] Error saving {STAGED_GAMES_FILE}: {e}", file=sys.stderr)
        return False

def check_single_game_health(game_id, staged_at_str=None):
    """
    Performs an HTTP and lifecycle health check on an individual Poker Now game ID.
    Returns a dict with 'healthy' (bool), 'reason' (str), and 'status_code' (int/None).
    """
    if not game_id:
        return {"healthy": False, "reason": "Missing game_id", "status_code": None}

    # 1. Age check
    if staged_at_str:
        try:
            staged_dt = datetime.datetime.fromisoformat(staged_at_str)
            age_hours = (datetime.datetime.now() - staged_dt).total_seconds() / 3600.0
            if age_hours > MAX_STAGING_AGE_HOURS:
                return {
                    "healthy": False,
                    "reason": f"Game exceeded maximum safe age ({age_hours:.1f}h > {MAX_STAGING_AGE_HOURS}h limit)",
                    "status_code": None,
                    "age_hours": round(age_hours, 1)
                }
        except Exception:
            pass

    # 2. HTTP Probe to pokernow.com/games/<game_id>
    url = f"https://www.pokernow.com/games/{game_id}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    )

    try:
        # Note: We do not follow redirects blindly if they redirect to home or an error page
        ctx = get_ssl_context()
        kwargs = {"timeout": HTTP_TIMEOUT_SECONDS}
        if ctx:
            kwargs["context"] = ctx
        with urllib.request.urlopen(req, **kwargs) as resp:
            final_url = resp.geturl()
            status_code = resp.getcode()
            
            # If redirected away from the game page, the game is invalid
            if f"/games/{game_id}" not in final_url:
                return {
                    "healthy": False,
                    "reason": f"Redirected to unexpected URL: {final_url}",
                    "status_code": status_code
                }

            # Read first chunk of HTML to check for expired message
            content_chunk = resp.read(8192).decode("utf-8", errors="ignore").lower()
            if "game has expired" in content_chunk or "sorry, this game has expired" in content_chunk:
                return {
                    "healthy": False,
                    "reason": "Poker Now reports room has expired",
                    "status_code": status_code
                }

            return {
                "healthy": True,
                "reason": "OK (active room)",
                "status_code": status_code
            }

    except urllib.error.HTTPError as he:
        if he.code == 429:
            # Poker Now rate limiter: back off 5 seconds and retry once
            time.sleep(5.0)
            try:
                with urllib.request.urlopen(req, **kwargs) as resp:
                    final_url = resp.geturl()
                    if f"/games/{game_id}" in final_url:
                        return {
                            "healthy": True,
                            "reason": "OK (active room, passed retry)",
                            "status_code": resp.getcode()
                        }
            except Exception:
                pass
            # If still rate-limited, the room is active but Poker Now is throttling requests. Do not alert as failed.
            return {
                "healthy": True,
                "reason": "OK (room active, throttled by rate limit)",
                "status_code": 429
            }

        return {
            "healthy": False,
            "reason": f"HTTP {he.code}: {he.reason}",
            "status_code": he.code
        }
    except Exception as e:
        # Network errors during probe (e.g. temporary DNS blip or unreachable host)
        # If age check passed, treat as healthy so a temporary network blip doesn't discard valid staged games
        err_msg = str(e)
        return {
            "healthy": True,
            "reason": f"Probe skipped / network error ({err_msg})",
            "status_code": None
        }

def verify_staged_batch_health(date_str, run_http_probe=True):
    """
    Verifies all tables for a specific date in staged_games.json.
    Returns dict with 'all_healthy' (bool), 'table_results' (list), and 'summary' (str).
    """
    staged = load_staged_games()
    entry = staged.get(date_str)
    if not entry:
        return {"all_healthy": False, "reason": f"No staged entry for {date_str}"}

    tables = entry.get("tables", [])
    staged_at = entry.get("staged_at")
    table_results = []
    all_healthy = True

    for idx, t in enumerate(tables):
        if idx > 0 and run_http_probe:
            time.sleep(2.5)  # 2.5s polite pacing between tables to avoid HTTP 429
        gid = t.get("game_id")
        if run_http_probe:
            res = check_single_game_health(gid, staged_at)
        else:
            # Age-only check if probes are skipped
            res = {"healthy": True, "reason": "Age check passed"}
            if staged_at:
                try:
                    staged_dt = datetime.datetime.fromisoformat(staged_at)
                    age_hours = (datetime.datetime.now() - staged_dt).total_seconds() / 3600.0
                    if age_hours > MAX_STAGING_AGE_HOURS:
                        res = {"healthy": False, "reason": f"Age {age_hours:.1f}h exceeds {MAX_STAGING_AGE_HOURS}h"}
                except Exception:
                    pass

        res["game_id"] = gid
        res["table_num"] = t.get("table_num")
        res["game_type"] = t.get("game_type")
        table_results.append(res)
        if not res["healthy"]:
            all_healthy = False

    entry["last_health_check"] = {
        "checked_at": datetime.datetime.now().isoformat(),
        "all_healthy": all_healthy,
        "results": table_results
    }
    save_staged_games(staged)

    return {
        "all_healthy": all_healthy,
        "date": date_str,
        "tables": table_results
    }

def get_staged_queue_summary():
    """Returns a list of all staged entries sorted by date with health badges."""
    staged = load_staged_games()
    now = datetime.datetime.now()
    summary = []

    for date_str, entry in sorted(staged.items()):
        staged_at_str = entry.get("staged_at")
        age_hours = 0
        age_days = 0
        if staged_at_str:
            try:
                staged_dt = datetime.datetime.fromisoformat(staged_at_str)
                age_hours = (now - staged_dt).total_seconds() / 3600.0
                age_days = age_hours / 24.0
            except Exception:
                pass

        # Calculate safety indicator
        if age_hours > MAX_STAGING_AGE_HOURS:
            health_badge = "expired"
        elif age_hours > 72:  # > 3 days
            health_badge = "aging"
        else:
            health_badge = "fresh"

        last_check = entry.get("last_health_check")
        verified_at = None
        is_verified = False
        all_healthy = True
        if last_check and isinstance(last_check, dict) and last_check.get("checked_at"):
            is_verified = True
            all_healthy = bool(last_check.get("all_healthy", True))
            try:
                dt = datetime.datetime.fromisoformat(last_check["checked_at"])
                verified_at = dt.strftime("%b %d, %I:%M %p")
            except Exception:
                verified_at = str(last_check["checked_at"])[:16].replace("T", " ")

        summary.append({
            "date": date_str,
            "day": entry.get("day", ""),
            "status": entry.get("status", "staged"),
            "table_count": len(entry.get("tables", [])),
            "tables": entry.get("tables", []),
            "staged_at": staged_at_str,
            "age_days": round(age_days, 1),
            "age_hours": round(age_hours, 1),
            "health_badge": health_badge,
            "last_health_check": last_check,
            "verified_at": verified_at,
            "is_verified": is_verified,
            "all_healthy": all_healthy
        })

    return summary

def add_or_update_staged_day(date_str, day_name, tables_list, description=None):
    """Adds or updates a staged day entry."""
    staged = load_staged_games()
    now_iso = datetime.datetime.now().isoformat()
    desc = description or datetime.datetime.strptime(date_str, "%Y-%m-%d").strftime("%m%d%y")

    staged[date_str] = {
        "date": date_str,
        "day": day_name.lower(),
        "description": desc,
        "staged_at": now_iso,
        "status": "staged",
        "game_ids": [t["game_id"] for t in tables_list if "game_id" in t],
        "tables": tables_list
    }
    save_staged_games(staged)
    return staged[date_str]

def purge_staged_day(date_str):
    """Purges a specific date from the staging queue."""
    staged = load_staged_games()
    if date_str in staged:
        removed = staged.pop(date_str)
        save_staged_games(staged)
        return True, removed
    return False, None

def purge_all_staged():
    """Purges all staged games."""
    save_staged_games({})
    return True

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Manage staged Poker Now games.")
    parser.add_argument("--list", action="store_true", help="List all staged games in the queue")
    parser.add_argument("--verify", type=str, help="Verify health of staged games for YYYY-MM-DD")
    parser.add_argument("--purge", type=str, help="Purge staged games for YYYY-MM-DD")
    parser.add_argument("--purge-all", action="store_true", help="Purge all staged games")
    args = parser.parse_args()

    if args.list:
        print(json.dumps(get_staged_queue_summary(), indent=2))
    elif args.verify:
        print(json.dumps(verify_staged_batch_health(args.verify), indent=2))
    elif args.purge:
        success, _ = purge_staged_day(args.purge)
        print(f"Purged {args.purge}: {success}")
    elif args.purge_all:
        purge_all_staged()
        print("Purged all staged games.")
    else:
        parser.print_help()
