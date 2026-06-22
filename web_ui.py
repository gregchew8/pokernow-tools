#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import threading
import time
import re
import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.parse

PORT = 8080
WORKING_DIR = "/Users/gregchew/pokernow"

# Thread-safe status trackers for running subprocesses
status_lock = threading.Lock()
running_tasks = {
    "announcer": False,
    "settlement": False
}

def run_script_in_background(task_name, cmd):
    global running_tasks
    with status_lock:
        if running_tasks[task_name]:
            return False
        running_tasks[task_name] = True
        
    def worker():
        try:
            print(f"[WebUI] Launching background task: {task_name} -> {' '.join(cmd)}")
            # Run the command and wait for it to complete
            subprocess.run(cmd, cwd=WORKING_DIR, check=True)
            print(f"[WebUI] Task {task_name} finished successfully.")
        except Exception as e:
            print(f"[WebUI] Error running task {task_name}: {e}")
        finally:
            with status_lock:
                running_tasks[task_name] = False
                
    t = threading.Thread(target=worker)
    t.daemon = True
    t.start()
    return True

def get_last_log_lines(filepath):
    if not os.path.exists(filepath):
        return "No log file found yet."
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        
        # We try to extract only the log contents starting from the most recent run
        started_marker = "=== Execution Started:"
        error_marker = "=== Error Occurred:"
        
        last_started_idx = content.rfind(started_marker)
        last_error_idx = content.rfind(error_marker)
        
        # Find the latest of the two headers
        latest_idx = max(last_started_idx, last_error_idx)
        
        if latest_idx != -1:
            return content[latest_idx:]
        else:
            # Fallback to the last 150 lines if no markers exist yet
            lines = content.splitlines()
            return "\n".join(lines[-150:])
    except Exception as e:
        return f"Error reading log file: {e}"

def parse_last_timestamp(content, marker):
    idx = content.rfind(marker)
    if idx == -1:
        return None
    # Extract the line containing the marker
    line_end = content.find("\n", idx)
    line = content[idx:line_end] if line_end != -1 else content[idx:]
    try:
        ts_str = line.split(marker)[1].split("===")[0].strip()
        import datetime
        return datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    except:
        return None

def triage_logs(a_out, a_err, s_out, s_err):
    import datetime
    
    # Default state: No runs or unknown state
    diagnosis = {
        "status": "info",
        "title": "Awaiting System Run",
        "explanation": "No active tasks have failed or succeeded yet in this monitoring session.",
        "steps": ["Click 'Start Table Setup' or 'Run Manual Settlement' to begin."]
    }

    # Extract last execution started and error timestamps
    a_start = parse_last_timestamp(a_out, "=== Execution Started:")
    a_error = parse_last_timestamp(a_err, "=== Error Occurred:")
    
    s_start = parse_last_timestamp(s_out, "=== Execution Started:")
    s_error = parse_last_timestamp(s_err, "=== Error Occurred:")

    # Determine if the last Announcer and Settlement runs failed
    # If the last start timestamp is greater than the last error timestamp, it succeeded!
    # (If a timestamp is None, we assume there is no event of that type).
    a_failed = False
    if a_error:
        if not a_start or a_error >= a_start:
            a_failed = True
            
    s_failed = False
    if s_error:
        if not s_start or s_error >= s_start:
            s_failed = True

    # If the last runs did not fail, check for successes to display success banners
    if not a_failed and not s_failed:
        # Check for successes
        if s_start and "settlement completed!" in s_out.lower():
            return {
                "status": "success",
                "title": "Settlement Runs Operational",
                "explanation": "The last settlement was completed successfully. Transactions were optimized, and payout emails were sent to the group address.",
                "steps": ["No actions required. All morning settlements are fully operational."]
            }
        if a_start and "success: created" in a_out.lower():
            return {
                "status": "success",
                "title": "Table Creations Operational",
                "explanation": "The last game night tables were created successfully, clipboard links updated, emails sent, and calendar events synced.",
                "steps": ["No actions required. Active table links are displayed in the panel above."]
            }
        return diagnosis

    # If we reached here, at least one of the runs failed.
    # Determine which ran more recently or failed last.
    # We will prioritize triaging the one that failed most recently.
    announcer_failed_last = True
    if a_failed and s_failed:
        if a_error and s_error and s_error > a_error:
            announcer_failed_last = False
    elif s_failed:
        announcer_failed_last = False

    if not announcer_failed_last:
        # Triage Settlement errors
        s_combined = (s_out + "\n" + s_err).lower()
        nickname_match = re.search(r"player with nickname '([^']+)' not found", s_combined)
        if nickname_match:
            nickname = nickname_match.group(1)
            return {
                "status": "error",
                "title": "Missing Player Payment Mapping",
                "explanation": f"The settlement engine failed because a player with the nickname '{nickname}' is not registered in your player database.",
                "steps": [
                    f"Open your player database Google Sheet.",
                    f"Add a new row mapping nickname '{nickname}' to their Venmo handle.",
                    "Wait 5 seconds for Google Drive sync, then click 'Run Manual Settlement' again."
                ]
            }

        if "smtpauthenticationerror" in s_combined:
            return {
                "status": "error",
                "title": "Email Authentication (SMTP) Failed (Settlement)",
                "explanation": "The email notification script could not log into your Gmail account during settlement. This is usually due to an incorrect or revoked Google App Password.",
                "steps": [
                    "Verify that EMAIL_SENDER is set correctly in your .env file.",
                    "Generate a new Google App Password from your Google Account security settings.",
                    "Update EMAIL_PASSWORD in your local .env file with the new 16-character App Password."
                ]
            }

        # General Settlement crash
        return {
            "status": "error",
            "title": "Settlement Execution Crash",
            "explanation": "The morning settlement task encountered an unexpected Python exception.",
            "steps": [
                "Review the Settlement Errors log below for the full traceback.",
                "Verify that your input data files (like payment_info.csv or local data files) are not corrupted."
            ]
        }
    else:
        # Triage Announcer errors
        a_combined = (a_out + "\n" + a_err).lower()
        if "smtpauthenticationerror" in a_combined:
            return {
                "status": "error",
                "title": "Email Authentication (SMTP) Failed (Announcer)",
                "explanation": "The email notification script could not log into your Gmail account during table announcements. This is usually due to an incorrect or revoked Google App Password.",
                "steps": [
                    "Verify that EMAIL_SENDER is set correctly in your .env file.",
                    "Generate a new Google App Password from your Google Account security settings.",
                    "Update EMAIL_PASSWORD in your local .env file with the new 16-character App Password."
                ]
            }

        if "executable doesn't exist" in a_combined or "looks like playwright was just installed" in a_combined:
            return {
                "status": "error",
                "title": "Playwright Browser Executable Missing",
                "explanation": "The automated browser binary was deleted or is missing from the local cache.",
                "steps": [
                    "Open a terminal on your Mac Mini.",
                    "Run the following command to reinstall Chromium to the persistent directory:",
                    "  PLAYWRIGHT_BROWSERS_PATH=./playwright-browsers python3 -m playwright install chromium"
                ]
            }

        if "timeout 25000ms exceeded" in a_combined or "failed to create/load game room" in a_combined:
            return {
                "status": "error",
                "title": "Poker Now Creation Timeout (Possible Anti-Bot Block)",
                "explanation": "The script timed out while waiting for Poker Now to create the table. This usually means the browser was blocked by a Cloudflare Turnstile captcha or your session has expired.",
                "steps": [
                    "Open a terminal on the Mac Mini.",
                    "Run 'python3 login.py' to launch a headed browser.",
                    "Log into Poker Now again in the visible browser window, then press ENTER in the terminal to save your login session."
                ]
            }

        if "google.auth.exceptions" in a_combined or "calendar_credentials.json" in a_combined:
            return {
                "status": "error",
                "title": "Google Calendar Authentication Failed",
                "explanation": "The announcer script could not authenticate with the Google Calendar API.",
                "steps": [
                    "Ensure that calendar_credentials.json is present in the root folder /Users/gregchew/pokernow.",
                    "Verify the CALENDAR_ID in your .env file matches the shared calendar's settings."
                ]
            }

        # General Announcer crash
        return {
            "status": "error",
            "title": "Game Announcer Execution Crash",
            "explanation": "The table creation task encountered an unexpected Python exception.",
            "steps": [
                "Review the Announcer Errors log below for the full traceback.",
                "Verify that schedule.json has correct syntax and formats."
            ]
        }

class WebUIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence standard HTTP requests logging in stdout
        pass

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(self.get_html_dashboard().encode("utf-8"))
        elif self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            
            # Load last created games
            last_games = {}
            games_json_path = os.path.join(WORKING_DIR, "last_created_games.json")
            if os.path.exists(games_json_path):
                try:
                    with open(games_json_path, "r") as f:
                        last_games = json.load(f)
                except:
                    pass

            with status_lock:
                a_stdout = get_last_log_lines(os.path.join(WORKING_DIR, "output/game_nights_stdout.log"))
                a_stderr = get_last_log_lines(os.path.join(WORKING_DIR, "output/game_nights_stderr.log"))
                s_stdout = get_last_log_lines(os.path.join(WORKING_DIR, "output/next_morning_stdout.log"))
                s_stderr = get_last_log_lines(os.path.join(WORKING_DIR, "output/next_morning_stderr.log"))
                
                diagnosis = triage_logs(a_stdout, a_stderr, s_stdout, s_stderr)
                
                # Extract timestamps
                a_start = parse_last_timestamp(a_stdout, "=== Execution Started:")
                a_error = parse_last_timestamp(a_stderr, "=== Error Occurred:")
                s_start = parse_last_timestamp(s_stdout, "=== Execution Started:")
                s_error = parse_last_timestamp(s_stderr, "=== Error Occurred:")
                
                a_err_current = False
                if a_error:
                    if not a_start or a_error >= a_start:
                        a_err_current = True
                
                s_err_current = False
                if s_error:
                    if not s_start or s_error >= s_start:
                        s_err_current = True

                status = {
                    "announcer_running": running_tasks["announcer"],
                    "settlement_running": running_tasks["settlement"],
                    "last_games": last_games,
                    "announcer_stdout": a_stdout,
                    "announcer_stderr": a_stderr,
                    "settlement_stdout": s_stdout,
                    "settlement_stderr": s_stderr,
                    "diagnosis": diagnosis,
                    "announcer_start_time": a_start.strftime("%Y-%m-%d %H:%M:%S") if a_start else None,
                    "announcer_error_time": a_error.strftime("%Y-%m-%d %H:%M:%S") if a_error else None,
                    "announcer_error_is_current": a_err_current,
                    "settlement_start_time": s_start.strftime("%Y-%m-%d %H:%M:%S") if s_start else None,
                    "settlement_error_time": s_error.strftime("%Y-%m-%d %H:%M:%S") if s_error else None,
                    "settlement_error_is_current": s_err_current,
                    "server_time": datetime.datetime.now().strftime("%A, %b %d, %Y - %I:%M:%S %p")
                }
            self.wfile.write(json.dumps(status).encode("utf-8"))
        elif self.path == "/api/schedule":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            schedule_path = os.path.join(WORKING_DIR, "schedule.json")
            schedule_data = {}
            if os.path.exists(schedule_path):
                try:
                    with open(schedule_path, "r") as f:
                        schedule_data = json.load(f)
                except Exception as e:
                    print(f"[WebUI] Error reading schedule.json: {e}")
            self.wfile.write(json.dumps(schedule_data).encode("utf-8"))
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        if self.path == "/api/run-announcer":
            cmd = [sys.executable, "announce_games.py"]
            success = run_script_in_background("announcer", cmd)
            self.send_response(200 if success else 409)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success}).encode("utf-8"))
        elif self.path == "/api/run-settlement":
            content_length = int(self.headers.get('Content-Length', 0))
            cmd = [sys.executable, "auto_settle.py"]
            if content_length > 0:
                try:
                    post_data = self.rfile.read(content_length)
                    payload = json.loads(post_data.decode("utf-8"))
                    desc = payload.get("description", "").strip()
                    gids = payload.get("game_ids", [])
                    if desc:
                        cmd += ["--description", desc]
                    if gids:
                        cmd += ["--game_ids"] + gids
                except Exception as e:
                    print(f"[WebUI] Error parsing run-settlement payload: {e}")
            else:
                cmd += ["--force"]

            success = run_script_in_background("settlement", cmd)
            self.send_response(200 if success else 409)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success}).encode("utf-8"))
        elif self.path == "/api/schedule":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                new_schedule = json.loads(post_data.decode("utf-8"))
                schedule_path = os.path.join(WORKING_DIR, "schedule.json")
                with open(schedule_path, "w") as f:
                    json.dump(new_schedule, f, indent=4)
                
                # Sync changes to drive
                subprocess.run(["./sync_to_drive.sh"], cwd=WORKING_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
        elif self.path == "/api/run-adhoc":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                adhoc_config = json.loads(post_data.decode("utf-8"))
                config_str = json.dumps(adhoc_config)
                cmd = [sys.executable, "announce_games.py", "--config", config_str, "--adhoc"]
                success = run_script_in_background("announcer", cmd)
                self.send_response(200 if success else 409)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": success}).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
        else:
            self.send_error(404, "Not Found")

    def get_html_dashboard(self):
        return r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Poker Now Control Panel</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0b0f19;
            --card-bg: rgba(22, 28, 45, 0.7);
            --border-color: rgba(255, 255, 255, 0.08);
            --text-color: #e2e8f0;
            --text-muted: #94a3b8;
            --primary: #4f46e5;
            --primary-hover: #6366f1;
            --success: #10b981;
            --danger: #ef4444;
            --glow: 0 0 20px rgba(79, 70, 229, 0.15);
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg-color);
            background-image: 
                radial-gradient(at 0% 0%, rgba(31, 41, 55, 0.3) 0, transparent 50%),
                radial-gradient(at 50% 0%, rgba(79, 70, 229, 0.05) 0, transparent 50%);
            color: var(--text-color);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 2rem 1rem;
        }

        .container {
            width: 100%;
            max-width: 900px;
            display: flex;
            flex-direction: column;
            gap: 2rem;
        }

        header {
            text-align: center;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--border-color);
        }

        h1 {
            font-size: 2.2rem;
            font-weight: 800;
            letter-spacing: -0.05em;
            background: linear-gradient(135deg, #fff 0%, #a5b4fc 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }

        .subtitle {
            color: var(--text-muted);
            font-size: 1rem;
        }

        .dashboard-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 1.5rem;
        }

        @media (min-width: 768px) {
            .dashboard-grid {
                grid-template-columns: 1fr 1fr;
            }
            .full-width {
                grid-column: span 2;
            }
        }

        .card {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem;
            backdrop-filter: blur(12px);
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }

        .card:hover {
            transform: translateY(-2px);
            box-shadow: var(--glow);
            border-color: rgba(79, 70, 229, 0.3);
        }

        h2 {
            font-size: 1.25rem;
            font-weight: 600;
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .status-badge {
            font-size: 0.75rem;
            padding: 0.25rem 0.6rem;
            border-radius: 20px;
            font-weight: 600;
            text-transform: uppercase;
        }

        .status-idle {
            background-color: rgba(148, 163, 184, 0.15);
            color: var(--text-muted);
            border: 1px solid rgba(148, 163, 184, 0.2);
        }

        .status-running {
            background-color: rgba(16, 185, 129, 0.15);
            color: var(--success);
            border: 1px solid rgba(16, 185, 129, 0.2);
            animation: pulse 1.5s infinite;
        }

        @keyframes pulse {
            0% { opacity: 0.6; }
            50% { opacity: 1; }
            100% { opacity: 0.6; }
        }

        .btn {
            display: block;
            width: 100%;
            padding: 0.8rem 1.5rem;
            font-size: 1rem;
            font-weight: 600;
            color: #fff;
            background: linear-gradient(135deg, var(--primary) 0%, #312e81 100%);
            border: none;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s ease;
            text-align: center;
            margin-top: 1rem;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }

        .btn:hover {
            background: linear-gradient(135deg, var(--primary-hover) 0%, var(--primary) 100%);
            transform: translateY(-1px);
        }

        .btn:disabled {
            background: #1e293b;
            color: var(--text-muted);
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }

        .games-list {
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
            margin-top: 0.5rem;
        }

        .game-item {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 8px;
            padding: 0.75rem 1rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .game-title {
            font-weight: 600;
            font-size: 0.95rem;
        }

        .game-link {
            font-size: 0.85rem;
            color: var(--primary-hover);
            text-decoration: none;
            border: 1px solid rgba(99, 102, 241, 0.2);
            padding: 0.25rem 0.6rem;
            border-radius: 4px;
            transition: all 0.2s;
        }

        .game-link:hover {
            background: rgba(99, 102, 241, 0.1);
            border-color: var(--primary-hover);
        }

        .console-container {
            margin-top: 1rem;
            position: relative;
        }

        .console-header {
            font-size: 0.85rem;
            color: var(--text-muted);
            margin-bottom: 0.25rem;
            font-weight: 600;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .copy-btn {
            font-size: 0.72rem;
            color: var(--text-muted);
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.08);
            padding: 0.2rem 0.6rem;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.2s ease;
            font-family: 'Outfit', sans-serif;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.02em;
        }

        .copy-btn:hover {
            background: rgba(99, 102, 241, 0.15);
            border-color: var(--primary-hover);
            color: #fff;
        }

        pre {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.8rem;
            background: #020617;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 1rem;
            max-height: 250px;
            overflow-y: auto;
            white-space: pre-wrap;
            word-break: break-all;
            color: #34d399;
        }

        .error-log pre {
            color: #f87171;
        }
        
        .no-games {
            color: var(--text-muted);
            font-style: italic;
            text-align: center;
            padding: 1rem 0;
            font-size: 0.95rem;
        }

        .badge {
            font-size: 0.7rem;
            padding: 0.15rem 0.4rem;
            border-radius: 4px;
            font-weight: 700;
            text-transform: uppercase;
            margin-left: 0.5rem;
            display: inline-block;
        }

        .badge-active {
            background-color: rgba(239, 68, 68, 0.2);
            color: #f87171;
            border: 1px solid rgba(239, 68, 68, 0.4);
        }

        .badge-stale {
            background-color: rgba(148, 163, 184, 0.15);
            color: var(--text-muted);
            border: 1px solid rgba(148, 163, 184, 0.3);
        }

        .badge-success {
            background-color: rgba(16, 185, 129, 0.15);
            color: var(--success);
            border: 1px solid rgba(16, 185, 129, 0.3);
        }

        .log-meta {
            font-size: 0.75rem;
            color: var(--text-muted);
            font-weight: normal;
            margin-left: auto;
            margin-right: 1rem;
        }

        .stale-log-box {
            opacity: 0.45;
            transition: opacity 0.25s ease;
        }

        .stale-log-box:hover {
            opacity: 1.0;
        }

        /* Schedule Editor & Adhoc Panel Styles */
        .collapsible-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
            padding: 1rem 0;
            user-select: none;
        }

        .collapsible-header::after {
            content: "▼";
            font-size: 0.8rem;
            color: var(--text-muted);
            transition: transform 0.2s ease;
        }

        .collapsible-header.active::after {
            transform: rotate(180deg);
        }

        .collapsible-content {
            display: none;
            padding-top: 1rem;
            border-top: 1px solid var(--border-color);
            margin-top: 0.5rem;
        }

        .schedule-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 1.5rem;
        }

        @media (min-width: 768px) {
            .schedule-grid {
                grid-template-columns: 1fr 1fr;
            }
        }

        .day-panel {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 1rem;
        }

        .day-title {
            font-size: 1rem;
            font-weight: 600;
            text-transform: capitalize;
            margin-bottom: 0.75rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            padding-bottom: 0.4rem;
        }

        .day-games {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }

        .game-row {
            display: flex;
            gap: 0.4rem;
            align-items: center;
        }

        .input-small {
            background: #020617;
            border: 1px solid var(--border-color);
            border-radius: 4px;
            color: #fff;
            padding: 0.3rem 0.5rem;
            font-size: 0.85rem;
            font-family: inherit;
        }

        select.input-small {
            cursor: pointer;
        }

        .input-stakes {
            width: 70px;
        }

        .btn-icon {
            background: none;
            border: none;
            color: var(--text-muted);
            cursor: pointer;
            font-size: 1rem;
            padding: 0.2rem;
            border-radius: 4px;
            transition: color 0.2s, background-color 0.2s;
        }

        .btn-icon:hover {
            color: var(--danger);
            background-color: rgba(239, 68, 68, 0.1);
        }

        .btn-add-game {
            display: block;
            width: 100%;
            background: rgba(255, 255, 255, 0.04);
            border: 1px dashed var(--border-color);
            border-radius: 6px;
            color: var(--text-muted);
            padding: 0.4rem;
            font-size: 0.8rem;
            cursor: pointer;
            text-align: center;
            transition: all 0.2s;
            margin-top: 0.5rem;
            font-weight: 600;
        }

        .btn-add-game:hover {
            border-color: var(--primary-hover);
            color: #fff;
            background: rgba(79, 70, 229, 0.1);
        }

        /* Adhoc form styling */
        .adhoc-builder {
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }

        .adhoc-tables {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }

        .btn-save-container {
            display: flex;
            justify-content: flex-end;
            gap: 1rem;
            margin-top: 1.5rem;
        }

        .btn-action {
            padding: 0.5rem 1rem;
            font-size: 0.9rem;
            font-weight: 600;
            border-radius: 6px;
            cursor: pointer;
            border: none;
            transition: all 0.2s;
        }

        .btn-primary {
            background: var(--primary);
            color: #fff;
        }

        .btn-primary:hover {
            background: var(--primary-hover);
        }

        .btn-secondary {
            background: rgba(255,255,255,0.08);
            color: var(--text-color);
            border: 1px solid var(--border-color);
        }

        .btn-secondary:hover {
            background: rgba(255,255,255,0.15);
        }

        /* Banner Styles */
        .banner {
            width: 100%;
            padding: 0.8rem 1rem;
            border-radius: 8px;
            font-weight: 600;
            font-size: 0.95rem;
            margin-bottom: 1.5rem;
            text-align: center;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
        }

        .banner-warning {
            background-color: rgba(245, 158, 11, 0.15);
            color: #fbbf24;
            border: 1px solid rgba(245, 158, 11, 0.3);
            box-shadow: 0 0 15px rgba(245, 158, 11, 0.08);
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Poker Now Control Panel</h1>
            <p class="subtitle">Tailscale Secure Remote Management</p>
            <div id="server-timestamp" style="font-family: 'JetBrains Mono', monospace; font-size: 1.05rem; color: #10b981; margin-top: 0.75rem; text-shadow: 0 0 10px rgba(16, 185, 129, 0.3); font-weight: bold;">Loading system time...</div>
        </header>

        <div id="override-banner" class="banner banner-warning" style="display: none;">
            ⚠️ Standard schedule is overridden for the night! Ad-hoc games are currently active.
        </div>

        <div class="dashboard-grid">
            <!-- Diagnostic Card -->
            <div id="diagnostic-card" class="card full-width" style="display: none;">
                <h2 id="diag-title" style="display: flex; align-items: center; gap: 0.5rem;">
                    Diagnostic Advisor
                </h2>
                <p id="diag-explanation" style="margin-bottom: 1rem; line-height: 1.5; font-size: 0.95rem;"></p>
                <div id="diag-steps-container" style="background: rgba(0,0,0,0.2); padding: 1rem; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);">
                    <div style="font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); margin-bottom: 0.5rem; font-weight: 600;">Recommended Steps to Resolve:</div>
                    <ul id="diag-steps" style="list-style-position: inside; display: flex; flex-direction: column; gap: 0.5rem; font-size: 0.9rem; line-height: 1.4;">
                    </ul>
                </div>
            </div>

            <!-- Game Announcer Card -->
            <div class="card">
                <h2>
                    <span>Game Announcer</span>
                    <span id="announcer-badge" class="status-badge status-idle">Idle</span>
                </h2>
                <p class="subtitle">Launches room creations & sends email announcements based on today's schedule config.</p>
                <button id="btn-announcer" class="btn" onclick="triggerTask('announcer')">Start Table Setup</button>
            </div>

            <!-- Settlement Card -->
            <div class="card">
                <h2>
                    <span>Payout Settlement</span>
                    <span id="settlement-badge" class="status-badge status-idle">Idle</span>
                </h2>
                <p class="subtitle">Manually downloads cashout logs for current tables, runs payouts optimization, and emails results.</p>
                <button id="btn-settlement" class="btn" onclick="triggerTask('settlement')">Run Manual Settlement</button>
            </div>

            <!-- Active Games Card -->
            <div class="card full-width">
                <h2>Active Game Tables <span id="active-date" style="font-size: 0.85rem; color: var(--text-muted);"></span></h2>
                <div id="active-games-container" class="games-list">
                    <!-- Loaded dynamically -->
                </div>
            </div>

            <!-- Schedule Editor Card -->
            <div class="card full-width">
                <h2 class="collapsible-header" id="schedule-header" onclick="toggleCollapsible('schedule-editor', 'schedule-header')">
                    <span>Main Schedule Editor</span>
                </h2>
                <div id="schedule-editor" class="collapsible-content">
                    <p class="subtitle" style="margin-bottom: 1.5rem;">Configure standard tables automatically scheduled for weekday runs.</p>
                    <div id="schedule-container" class="schedule-grid">
                        <!-- Loaded dynamically -->
                    </div>
                    <div class="btn-save-container">
                        <button class="btn-action btn-secondary" onclick="loadSchedule()">Reset Changes</button>
                        <button class="btn-action btn-primary" onclick="saveSchedule()">Save Schedule</button>
                    </div>
                </div>
            </div>

            <!-- Adhoc Game Launcher Card -->
            <div class="card full-width">
                <h2 class="collapsible-header" id="adhoc-header" onclick="toggleCollapsible('adhoc-launcher', 'adhoc-header')">
                    <span>Launch Ad-hoc Session</span>
                </h2>
                <div id="adhoc-launcher" class="collapsible-content">
                    <p class="subtitle" style="margin-bottom: 1rem;">Configure and start a one-time game session tonight with custom stakes.</p>
                    <p style="background: rgba(245, 158, 11, 0.08); border-left: 4px solid #fbbf24; padding: 0.8rem 1rem; border-radius: 4px; font-size: 0.9rem; line-height: 1.5; color: #f59e0b; margin-bottom: 1.25rem;"><strong>💡 Note:</strong> Launching an ad-hoc session will override the standard calendar schedule for tonight. Standard automatic runs will be bypassed in favor of these custom configurations.</p>
                    <div class="adhoc-builder">
                        <div id="adhoc-tables-container" class="adhoc-tables">
                            <!-- Rows added dynamically -->
                        </div>
                        <button class="btn-add-game" onclick="addAdhocRow()">+ Add Another Table</button>
                        
                        <div style="display: flex; align-items: flex-start; gap: 0.5rem; margin-top: 1rem; font-size: 0.9rem; color: var(--text-muted);">
                            <input type="checkbox" id="chk-adhoc-acknowledge" onchange="toggleAdhocButton()" style="margin-top: 0.2rem; cursor: pointer;">
                            <label for="chk-adhoc-acknowledge" style="cursor: pointer; line-height: 1.4;">I acknowledge that launching this ad-hoc session will override the standard schedule for tonight and I explicitly want to proceed.</label>
                        </div>

                        <div class="btn-save-container">
                            <button id="btn-launch-adhoc" class="btn-action btn-primary" style="padding: 0.7rem 1.5rem;" onclick="launchAdhoc()" disabled>Launch Ad-hoc Session</button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Logs Section -->
            <div class="card full-width">
                <h2>System Logs & Outputs</h2>
                
                <div id="announcer-stdout-container" class="console-container">
                    <div class="console-header">
                        <span>Announcer Logs (Stdout)</span>
                        <span id="announcer-stdout-time" class="log-meta"></span>
                        <button class="copy-btn" onclick="copyConsole('announcer-stdout', this)">Copy</button>
                    </div>
                    <pre id="announcer-stdout">Loading logs...</pre>
                </div>
                
                <div id="announcer-stderr-container" class="console-container error-log">
                    <div class="console-header">
                        <span>Announcer Errors (Stderr) <span id="announcer-stderr-badge" class="badge"></span></span>
                        <span id="announcer-stderr-time" class="log-meta"></span>
                        <button class="copy-btn" onclick="copyConsole('announcer-stderr', this)">Copy</button>
                    </div>
                    <pre id="announcer-stderr">Loading logs...</pre>
                </div>
                
                <hr style="margin: 2rem 0; border: none; border-top: 1px solid var(--border-color);">
                
                <div id="settlement-stdout-container" class="console-container">
                    <div class="console-header">
                        <span>Settlement Logs (Stdout)</span>
                        <span id="settlement-stdout-time" class="log-meta"></span>
                        <button class="copy-btn" onclick="copyConsole('settlement-stdout', this)">Copy</button>
                    </div>
                    <pre id="settlement-stdout">Loading logs...</pre>
                </div>
                
                <div id="settlement-stderr-container" class="console-container error-log">
                    <div class="console-header">
                        <span>Settlement Errors (Stderr) <span id="settlement-stderr-badge" class="badge"></span></span>
                        <span id="settlement-stderr-time" class="log-meta"></span>
                        <button class="copy-btn" onclick="copyConsole('settlement-stderr', this)">Copy</button>
                    </div>
                    <pre id="settlement-stderr">Loading logs...</pre>
                </div>
            </div>
        </div>
    </div>

    <script>
        function updateDashboard() {
            fetch('/api/status')
                .then(res => res.json())
                .then(data => {
                    // Update Diagnosis Card
                    const diagCard = document.getElementById('diagnostic-card');
                    if (data.diagnosis && data.diagnosis.status !== 'info') {
                        diagCard.style.display = 'block';
                        
                        const diagTitle = document.getElementById('diag-title');
                        const diagExplanation = document.getElementById('diag-explanation');
                        const diagSteps = document.getElementById('diag-steps');
                        
                        diagExplanation.textContent = data.diagnosis.explanation;
                        
                        // Set colors and titles based on status
                        if (data.diagnosis.status === 'error') {
                            diagTitle.innerHTML = `⚠️ Diagnostic Advisor: <span style="color: var(--danger); font-weight: 800;">${data.diagnosis.title}</span>`;
                            diagCard.style.borderColor = 'rgba(239, 68, 68, 0.4)';
                            diagCard.style.boxShadow = '0 0 25px rgba(239, 68, 68, 0.15)';
                        } else if (data.diagnosis.status === 'success') {
                            diagTitle.innerHTML = `✅ Diagnostic Advisor: <span style="color: var(--success); font-weight: 800;">${data.diagnosis.title}</span>`;
                            diagCard.style.borderColor = 'rgba(16, 185, 129, 0.4)';
                            diagCard.style.boxShadow = '0 0 25px rgba(16, 185, 129, 0.15)';
                        }
                        
                        // Populate steps
                        diagSteps.innerHTML = '';
                        data.diagnosis.steps.forEach(step => {
                            const li = document.createElement('li');
                            li.textContent = step;
                            diagSteps.appendChild(li);
                        });
                    } else {
                        diagCard.style.display = 'none';
                    }

                    // Update Announcer Status
                    const announcerBadge = document.getElementById('announcer-badge');
                    const btnAnnouncer = document.getElementById('btn-announcer');
                    if (data.announcer_running) {
                        announcerBadge.textContent = 'Running';
                        announcerBadge.className = 'status-badge status-running';
                        btnAnnouncer.disabled = true;
                        btnAnnouncer.textContent = 'Setting up Tables...';
                    } else {
                        announcerBadge.textContent = 'Idle';
                        announcerBadge.className = 'status-badge status-idle';
                        btnAnnouncer.disabled = data.settlement_running;
                        btnAnnouncer.textContent = 'Start Table Setup';
                    }

                    // Update Settlement Status
                    const settlementBadge = document.getElementById('settlement-badge');
                    const btnSettlement = document.getElementById('btn-settlement');
                    if (data.settlement_running) {
                        settlementBadge.textContent = 'Running';
                        settlementBadge.className = 'status-badge status-running';
                        btnSettlement.disabled = true;
                        btnSettlement.textContent = 'Calculating Payouts...';
                    } else {
                        settlementBadge.textContent = 'Idle';
                        settlementBadge.className = 'status-badge status-idle';
                        btnSettlement.disabled = data.announcer_running;
                        btnSettlement.textContent = 'Run Manual Settlement';
                    }

                    // Update Logs
                    document.getElementById('announcer-stdout').textContent = data.announcer_stdout;
                    document.getElementById('announcer-stderr').textContent = data.announcer_stderr;
                    document.getElementById('settlement-stdout').textContent = data.settlement_stdout;
                    document.getElementById('settlement-stderr').textContent = data.settlement_stderr;

                    // Announcer Logs Metadata & Badges
                    const aStdoutTime = document.getElementById('announcer-stdout-time');
                    const aStderrTime = document.getElementById('announcer-stderr-time');
                    const aStderrBadge = document.getElementById('announcer-stderr-badge');
                    const aStderrContainer = document.getElementById('announcer-stderr-container');

                    if (data.announcer_start_time) {
                        aStdoutTime.textContent = 'Last Run: ' + data.announcer_start_time;
                    } else {
                        aStdoutTime.textContent = '';
                    }

                    if (data.announcer_error_time) {
                        aStderrTime.textContent = 'Error At: ' + data.announcer_error_time;
                    } else {
                        aStderrTime.textContent = '';
                    }

                    if (data.announcer_error_time) {
                        if (data.announcer_error_is_current) {
                            aStderrBadge.textContent = 'Active Error';
                            aStderrBadge.className = 'badge badge-active';
                            aStderrContainer.classList.remove('stale-log-box');
                        } else {
                            aStderrBadge.textContent = 'Stale / Resolved';
                            aStderrBadge.className = 'badge badge-stale';
                            aStderrContainer.classList.add('stale-log-box');
                        }
                    } else {
                        if (data.announcer_start_time) {
                            aStderrBadge.textContent = 'Success';
                            aStderrBadge.className = 'badge badge-success';
                        } else {
                            aStderrBadge.textContent = '';
                            aStderrBadge.className = 'badge';
                        }
                        aStderrContainer.classList.remove('stale-log-box');
                    }

                    // Settlement Logs Metadata & Badges
                    const sStdoutTime = document.getElementById('settlement-stdout-time');
                    const sStderrTime = document.getElementById('settlement-stderr-time');
                    const sStderrBadge = document.getElementById('settlement-stderr-badge');
                    const sStderrContainer = document.getElementById('settlement-stderr-container');

                    if (data.settlement_start_time) {
                        sStdoutTime.textContent = 'Last Run: ' + data.settlement_start_time;
                    } else {
                        sStdoutTime.textContent = '';
                    }

                    if (data.settlement_error_time) {
                        sStderrTime.textContent = 'Error At: ' + data.settlement_error_time;
                    } else {
                        sStderrTime.textContent = '';
                    }

                    if (data.settlement_error_time) {
                        if (data.settlement_error_is_current) {
                            sStderrBadge.textContent = 'Active Error';
                            sStderrBadge.className = 'badge badge-active';
                            sStderrContainer.classList.remove('stale-log-box');
                        } else {
                            sStderrBadge.textContent = 'Stale / Resolved';
                            sStderrBadge.className = 'badge badge-stale';
                            sStderrContainer.classList.add('stale-log-box');
                        }
                    } else {
                        if (data.settlement_start_time) {
                            sStderrBadge.textContent = 'Success';
                            sStderrBadge.className = 'badge badge-success';
                        } else {
                            sStderrBadge.textContent = '';
                            sStderrBadge.className = 'badge';
                        }
                        sStderrContainer.classList.remove('stale-log-box');
                    }

                    // Update Active Games
                    const activeContainer = document.getElementById('active-games-container');
                    const activeDate = document.getElementById('active-date');
                    activeContainer.innerHTML = '';
                    
                    if (data.last_games && data.last_games.tables && data.last_games.tables.length > 0) {
                        activeDate.textContent = `(Game Date: ${data.last_games.date})`;
                        data.last_games.tables.forEach(t => {
                            const item = document.createElement('div');
                            item.className = 'game-item';
                            
                            const title = document.createElement('span');
                            title.className = 'game-title';
                            const stakes = (t.sb && t.bb) ? ` (${t.sb}/${t.bb})` : '';
                            title.textContent = `${t.game_type.toUpperCase()}${stakes} - Table ${t.table_num}`;
                            
                            const link = document.createElement('a');
                            link.className = 'game-link';
                            link.href = `https://www.pokernow.club/games/${t.game_id}`;
                            link.target = '_blank';
                            link.textContent = 'Open Room';
                            
                            item.appendChild(title);
                            item.appendChild(link);
                            activeContainer.appendChild(item);
                        });
                    } else {
                        activeDate.textContent = '';
                        activeContainer.innerHTML = '<div class="no-games">No active tables found. Click "Start Table Setup" to create them.</div>';
                    }
                    
                    // Update server timestamp
                    document.getElementById('server-timestamp').textContent = data.server_time || 'Offline';

                    // Update override banner
                    const overrideBanner = document.getElementById('override-banner');
                    if (data.last_games && data.last_games.is_adhoc) {
                        overrideBanner.style.display = 'flex';
                    } else {
                        overrideBanner.style.display = 'none';
                    }
                })
                .catch(err => console.error("Error updating dashboard:", err));
        }

        function triggerTask(taskName) {
            if (taskName === 'settlement') {
                const today = new Date();
                const yesterday = new Date(today);
                yesterday.setDate(today.getDate() - 1);
                
                const yyyy = yesterday.getFullYear();
                let mm = yesterday.getMonth() + 1;
                let dd = yesterday.getDate();
                
                if (dd < 10) dd = '0' + dd;
                if (mm < 10) mm = '0' + mm;
                
                const yearShort = String(yyyy).substring(2);
                const defaultDesc = `${mm}${dd}${yearShort}`;
                
                const desc = prompt("Enter settlement description/date (MMDDYY):", defaultDesc);
                if (desc === null) {
                    updateDashboard();
                    return;
                }
                
                const rawInput = prompt("Enter Game URLs or Game IDs (separated by spaces or commas):");
                if (rawInput === null) {
                    updateDashboard();
                    return;
                }
                
                const parsedIds = [];
                const tokens = rawInput.split(/[\s,\n]+/);
                tokens.forEach(tok => {
                    let clean = tok.trim();
                    if (!clean) return;
                    if (clean.includes("/games/")) {
                        const parts = clean.split("/games/");
                        if (parts.length > 1) {
                            clean = parts[1].split(/[?#]/)[0];
                        }
                    }
                    if (clean) {
                        parsedIds.push(clean);
                    }
                });
                
                if (parsedIds.length === 0) {
                    alert("No valid game IDs could be parsed from your input.");
                    updateDashboard();
                    return;
                }
                
                document.getElementById('btn-announcer').disabled = true;
                document.getElementById('btn-settlement').disabled = true;
                
                fetch('/api/run-settlement', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        description: desc.trim(),
                        game_ids: parsedIds
                    })
                })
                .then(res => {
                    if (res.ok) {
                        alert("Manual settlement calculation triggered successfully!");
                    } else {
                        alert("Failed to start settlement. Task is already running or conflict occurred.");
                    }
                    updateDashboard();
                })
                .catch(err => {
                    alert("Error triggering settlement: " + err);
                    updateDashboard();
                });
                
                return;
            }

            const endpoint = '/api/run-announcer';
            document.getElementById('btn-announcer').disabled = true;
            document.getElementById('btn-settlement').disabled = true;

            fetch(endpoint, { method: 'POST' })
                .then(res => {
                    if (res.ok) {
                        updateDashboard();
                    } else {
                        alert("Failed to start task. Task is already running or conflict occurred.");
                    }
                })
                .catch(err => {
                    alert("Error triggering task: " + err);
                    updateDashboard();
                });
        }

        function copyConsole(id, btn) {
            const pre = document.getElementById(id);
            if (!pre) return;
            const text = pre.textContent;
            navigator.clipboard.writeText(text).then(() => {
                const originalText = btn.textContent;
                btn.textContent = 'Copied!';
                btn.style.color = 'var(--success)';
                btn.style.borderColor = 'var(--success)';
                setTimeout(() => {
                    btn.textContent = originalText;
                    btn.style.color = '';
                    btn.style.borderColor = '';
                }, 2000);
            }).catch(err => {
                console.error('Failed to copy text: ', err);
            });
        }

        function toggleCollapsible(contentId, headerId) {
            const content = document.getElementById(contentId);
            const header = document.getElementById(headerId);
            if (content.style.display === 'block') {
                content.style.display = 'none';
                header.classList.remove('active');
            } else {
                content.style.display = 'block';
                header.classList.add('active');
                if (contentId === 'schedule-editor') {
                    loadSchedule();
                } else if (contentId === 'adhoc-launcher') {
                    initAdhocBuilder();
                }
            }
        }

        const ALL_DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];

        function loadSchedule() {
            fetch('/api/schedule')
                .then(res => res.json())
                .then(schedule => {
                    const container = document.getElementById('schedule-container');
                    container.innerHTML = '';
                    
                    ALL_DAYS.forEach(day => {
                        const panel = document.createElement('div');
                        panel.className = 'day-panel';
                        
                        const title = document.createElement('div');
                        title.className = 'day-title';
                        title.innerHTML = `<span>${day}</span>`;
                        panel.appendChild(title);
                        
                        const gamesDiv = document.createElement('div');
                        gamesDiv.className = 'day-games';
                        gamesDiv.id = `games-${day}`;
                        panel.appendChild(gamesDiv);
                        
                        const addBtn = document.createElement('button');
                        addBtn.className = 'btn-add-game';
                        addBtn.textContent = '+ Add Table';
                        addBtn.onclick = () => addScheduleGame(day);
                        panel.appendChild(addBtn);
                        
                        container.appendChild(panel);

                        // Populate existing games
                        if (schedule[day] && Array.isArray(schedule[day])) {
                            schedule[day].forEach(g => {
                                addScheduleGame(day, g.type, g.sb, g.bb);
                            });
                        }
                    });
                })
                .catch(err => console.error("Error loading schedule:", err));
        }

        function addScheduleGame(day, type="nlh", sb="0.25", bb="0.50") {
            const gamesDiv = document.getElementById(`games-${day}`);
            if (!gamesDiv) return;
            
            const row = document.createElement('div');
            row.className = 'game-row';
            
            row.innerHTML = `
                <select class="input-small game-type">
                    <option value="nlh" ${type === 'nlh' ? 'selected' : ''}>NLH</option>
                    <option value="plo" ${type === 'plo' ? 'selected' : ''}>PLO</option>
                    <option value="plo8" ${type === 'plo8' ? 'selected' : ''}>PLO8</option>
                </select>
                <input type="text" class="input-small input-stakes game-sb" placeholder="SB" value="${sb}">
                <span style="font-size:0.8rem;color:var(--text-muted);">/</span>
                <input type="text" class="input-small input-stakes game-bb" placeholder="BB" value="${bb}">
                <button class="btn-icon" onclick="this.parentElement.remove()" title="Remove game">✕</button>
            `;
            gamesDiv.appendChild(row);
        }

        function saveSchedule() {
            const newSchedule = {};
            
            ALL_DAYS.forEach(day => {
                const gamesDiv = document.getElementById(`games-${day}`);
                if (!gamesDiv) return;
                
                const rows = gamesDiv.getElementsByClassName('game-row');
                if (rows.length > 0) {
                    newSchedule[day] = [];
                    Array.from(rows).forEach(row => {
                        const type = row.querySelector('.game-type').value;
                        const sb = row.querySelector('.game-sb').value.trim();
                        const bb = row.querySelector('.game-bb').value.trim();
                        if (type && sb && bb) {
                            newSchedule[day].push({ type, sb, bb });
                        }
                    });
                }
            });
            
            fetch('/api/schedule', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(newSchedule)
            })
            .then(res => {
                if (res.ok) {
                    alert("Schedule saved successfully!");
                    loadSchedule();
                } else {
                    alert("Failed to save schedule.");
                }
            })
            .catch(err => alert("Error saving schedule: " + err));
        }

        function initAdhocBuilder() {
            const container = document.getElementById('adhoc-tables-container');
            if (container.children.length === 0) {
                addAdhocRow();
            }
        }

        function addAdhocRow(type="nlh", sb="0.25", bb="0.50") {
            const container = document.getElementById('adhoc-tables-container');
            const row = document.createElement('div');
            row.className = 'game-row';
            
            row.innerHTML = `
                <select class="input-small adhoc-type">
                    <option value="nlh" ${type === 'nlh' ? 'selected' : ''}>NLH</option>
                    <option value="plo" ${type === 'plo' ? 'selected' : ''}>PLO</option>
                    <option value="plo8" ${type === 'plo8' ? 'selected' : ''}>PLO8</option>
                </select>
                <input type="text" class="input-small input-stakes adhoc-sb" placeholder="SB" value="${sb}">
                <span style="font-size:0.8rem;color:var(--text-muted);">/</span>
                <input type="text" class="input-small input-stakes adhoc-bb" placeholder="BB" value="${bb}">
                <button class="btn-icon" onclick="this.parentElement.remove()" title="Remove table">✕</button>
            `;
            container.appendChild(row);
        }

        function toggleAdhocButton() {
            const checked = document.getElementById('chk-adhoc-acknowledge').checked;
            document.getElementById('btn-launch-adhoc').disabled = !checked;
        }

        function launchAdhoc() {
            const container = document.getElementById('adhoc-tables-container');
            const rows = container.getElementsByClassName('game-row');
            
            if (rows.length === 0) {
                alert("Please add at least one table before launching.");
                return;
            }
            
            const adhocConfig = [];
            let isValid = true;
            
            Array.from(rows).forEach(row => {
                const type = row.querySelector('.adhoc-type').value;
                const sb = row.querySelector('.adhoc-sb').value.trim();
                const bb = row.querySelector('.adhoc-bb').value.trim();
                
                if (!type || !sb || !bb) {
                    isValid = false;
                } else {
                    adhocConfig.push({ type, sb, bb });
                }
            });
            
            if (!isValid) {
                alert("Please fill in type, SB, and BB for all tables.");
                return;
            }
            
            // Disable launch button and announcer button optimistically
            document.getElementById('btn-launch-adhoc').disabled = true;
            document.getElementById('btn-announcer').disabled = true;
            
            fetch('/api/run-adhoc', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(adhocConfig)
            })
            .then(res => {
                if (res.ok) {
                    alert("Ad-hoc game night creation launched successfully!");
                    document.getElementById('announcer-stderr-container').classList.remove('stale-log-box');
                    // Reset acknowledgement checkbox
                    document.getElementById('chk-adhoc-acknowledge').checked = false;
                    toggleAdhocButton();
                } else {
                    alert("Failed to launch ad-hoc task. Another announcer/settlement task may be running.");
                    document.getElementById('btn-launch-adhoc').disabled = false;
                }
                updateDashboard();
            })
            .catch(err => {
                alert("Error launching task: " + err);
                document.getElementById('btn-launch-adhoc').disabled = false;
                updateDashboard();
            });
        }

        // Periodically refresh dashboard every 2 seconds
        setInterval(updateDashboard, 2000);
        updateDashboard();
    </script>
</body>
</html>
"""

def main():
    server_address = ("", PORT)
    httpd = HTTPServer(server_address, WebUIHandler)
    print(f"[WebUI] Server running at http://localhost:{PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("[WebUI] Stopping server...")
        httpd.server_close()

if __name__ == "__main__":
    main()
