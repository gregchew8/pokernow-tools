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
import smtplib
from email.mime.text import MIMEText

PORT = 8081
WORKING_DIR = os.path.dirname(os.path.abspath(__file__))

# Load local environment variables from .env
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

load_env()
AGENT_TOKEN = os.environ.get("AGENT_TOKEN")
if not AGENT_TOKEN:
    print("[WARNING] AGENT_TOKEN is not set in environment or .env file!")
def log_admin_activity(email, action, details="", ip=""):
    activity_file = os.path.join(WORKING_DIR, "output", "admin_activity.json")
    os.makedirs(os.path.dirname(activity_file), exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = {
        "time": timestamp,
        "email": email or "Unknown Admin",
        "action": action,
        "details": details,
        "ip": ip or "Unknown IP"
    }
    logs = []
    try:
        if os.path.exists(activity_file):
            with open(activity_file, "r") as f:
                logs = json.load(f)
    except Exception as e:
        print(f"[Agent] Error reading admin_activity.json: {e}")
    logs.insert(0, entry)
    logs = logs[:500]
    try:
        with open(activity_file, "w") as f:
            json.dump(logs, f, indent=2)
    except Exception as e:
        print(f"[Agent] Error writing to admin_activity.json: {e}")
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
        
    if task_name == "announcer":
        stdout_path = os.path.join(WORKING_DIR, "output/game_nights_stdout.log")
        stderr_path = os.path.join(WORKING_DIR, "output/game_nights_stderr.log")
    elif task_name == "settlement":
        stdout_path = os.path.join(WORKING_DIR, "output/next_morning_stdout.log")
        stderr_path = os.path.join(WORKING_DIR, "output/next_morning_stderr.log")
    else:
        stdout_path = None
        stderr_path = None

    def worker():
        try:
            print(f"[Agent] Launching background task: {task_name} -> {' '.join(cmd)}")
            out_f = open(stdout_path, "a", encoding="utf-8") if stdout_path else None
            err_f = open(stderr_path, "a", encoding="utf-8") if stderr_path else None
            try:
                subprocess.run(cmd, cwd=WORKING_DIR, check=True, stdout=out_f, stderr=err_f)
            finally:
                if out_f: out_f.close()
                if err_f: err_f.close()
            print(f"[Agent] Task {task_name} finished successfully.")
        except Exception as e:
            print(f"[Agent] Error running task {task_name}: {e}")
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
        
        started_marker = "=== Execution Started:"
        error_marker = "=== Error Occurred:"
        
        last_started_idx = content.rfind(started_marker)
        last_error_idx = content.rfind(error_marker)
        
        latest_idx = max(last_started_idx, last_error_idx)
        
        if latest_idx != -1:
            return content[latest_idx:]
        else:
            lines = content.splitlines()
            return "\n".join(lines[-150:])
    except Exception as e:
        return f"Error reading log file: {e}"

def parse_last_timestamp(content, marker):
    idx = content.rfind(marker)
    if idx == -1:
        return None
    line_end = content.find("\n", idx)
    line = content[idx:line_end] if line_end != -1 else content[idx:]
    try:
        ts_str = line.split(marker)[1].split("===")[0].strip()
        return datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    except:
        return None

ACKNOWLEDGED_ERRORS_FILE = os.path.join(WORKING_DIR, "data/acknowledged_errors.json")

def load_acknowledged_errors():
    if os.path.exists(ACKNOWLEDGED_ERRORS_FILE):
        try:
            with open(ACKNOWLEDGED_ERRORS_FILE, "r") as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def save_acknowledged_error(error_id):
    acknowledged = load_acknowledged_errors()
    acknowledged.add(error_id)
    os.makedirs(os.path.dirname(ACKNOWLEDGED_ERRORS_FILE), exist_ok=True)
    try:
        with open(ACKNOWLEDGED_ERRORS_FILE, "w") as f:
            json.dump(list(acknowledged), f)
        return True
    except Exception as e:
        print(f"[Agent] Error saving acknowledged error: {e}")
        return False

def triage_single_error(source, out_content, err_content):
    combined = (out_content + "\n" + err_content).lower()
    if source == "settlement":
        nickname_match = re.search(r"player with nickname '([^']+)' not found", combined)
        if nickname_match:
            nickname = nickname_match.group(1)
            return {
                "title": "Missing Player Payment Mapping",
                "explanation": f"The settlement engine failed because a player with the nickname '{nickname}' is not registered in your player database.",
                "steps": [
                    "Open your player database Google Sheet.",
                    f"Add a new row mapping nickname <span class='copyable-badge' onclick='copyTextToClipboard(\"{nickname}\")' title='Click to copy nickname'>{nickname} 📋</span> to their Venmo handle.",
                    "Wait 5 seconds for Google Drive sync, then click 'Run Manual Settlement' again."
                ]
            }
        if "smtpauthenticationerror" in combined:
            return {
                "title": "Email Authentication (SMTP) Failed (Settlement)",
                "explanation": "The email notification script could not log into your Gmail account during settlement. This is usually due to an incorrect or revoked Google App Password.",
                "steps": [
                    "Verify that EMAIL_SENDER is set correctly in your .env file.",
                    "Generate a new Google App Password from your Google Account security settings.",
                    "Update EMAIL_PASSWORD in your local .env file with the new 16-character App Password."
                ]
            }
        return {
            "title": "Settlement Execution Crash",
            "explanation": "The morning settlement task encountered an unexpected Python exception.",
            "steps": [
                "Review the Settlement Errors log below for the full traceback.",
                "Verify that your input data files (like payment_info.csv or local data files) are not corrupted."
            ]
        }
    else: # announcer
        if "smtpauthenticationerror" in combined:
            return {
                "title": "Email Authentication (SMTP) Failed (Announcer)",
                "explanation": "The email notification script could not log into your Gmail account during table announcements. This is usually due to an incorrect or revoked Google App Password.",
                "steps": [
                    "Verify that EMAIL_SENDER is set correctly in your .env file.",
                    "Generate a new Google App Password from your Google Account security settings.",
                    "Update EMAIL_PASSWORD in your local .env file with the new 16-character App Password."
                ]
            }
        if "executable doesn't exist" in combined or "looks like playwright was just installed" in combined:
            return {
                "title": "Playwright Browser Executable Missing",
                "explanation": "The automated browser binary was deleted or is missing from the local cache.",
                "steps": [
                    "Open a terminal on your Mac Mini.",
                    "Run the following command to reinstall Chromium to the persistent directory:",
                    "  PLAYWRIGHT_BROWSERS_PATH=./playwright-browsers python3 -m playwright install chromium"
                ]
            }
        if "timeout 25000ms exceeded" in combined or "failed to create/load game room" in combined or "targetclosederror" in combined:
            return {
                "title": "Poker Now Creation Timeout (Possible Anti-Bot Block)",
                "explanation": "The script timed out while waiting for Poker Now to create the table. This usually means the browser was blocked by a Cloudflare Turnstile captcha or your session has expired.",
                "steps": [
                    "Open a terminal on the Mac Mini.",
                    "Run 'python3 login.py' to launch a headed browser.",
                    "Log into Poker Now again in the visible browser window, then press ENTER in the terminal to save your login session."
                ]
            }
        if "google.auth.exceptions" in combined or "calendar_credentials.json" in combined:
            return {
                "title": "Google Calendar Authentication Failed",
                "explanation": "The announcer script could not authenticate with the Google Calendar API.",
                "steps": [
                    "Ensure that calendar_credentials.json is present in the root folder.",
                    "Verify the CALENDAR_ID in your .env file matches the shared calendar's settings."
                ]
            }
        return {
            "title": "Game Announcer Execution Crash",
            "explanation": "The table creation task encountered an unexpected Python exception.",
            "steps": [
                "Review the Announcer Errors log below for the full traceback.",
                "Verify that schedule.json has correct syntax and formats."
            ]
        }

def parse_all_errors_from_logs(source):
    if source == "announcer":
        stderr_path = os.path.join(WORKING_DIR, "output/game_nights_stderr.log")
        stdout_path = os.path.join(WORKING_DIR, "output/game_nights_stdout.log")
    else:
        stderr_path = os.path.join(WORKING_DIR, "output/next_morning_stderr.log")
        stdout_path = os.path.join(WORKING_DIR, "output/next_morning_stdout.log")

    if not os.path.exists(stderr_path):
        return []
    try:
        with open(stderr_path, "r", encoding="utf-8") as f:
            content = f.read()
    except:
        return []

    errors = []
    pattern = r"=== Error Occurred:\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s*==="
    matches = list(re.finditer(pattern, content))

    stdout_content = ""
    if os.path.exists(stdout_path):
        try:
            with open(stdout_path, "r", encoding="utf-8") as sf:
                stdout_content = sf.read()
        except:
            pass

    for i, m in enumerate(matches):
        ts_str = m.group(1)
        start_idx = m.end()
        end_idx = matches[i+1].start() if i + 1 < len(matches) else len(content)
        err_chunk = content[start_idx:end_idx].strip()

        stdout_chunk = ""
        if stdout_content:
            start_pattern = r"=== Execution Started:\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s*==="
            start_matches = list(re.finditer(start_pattern, stdout_content))
            best_match = None
            for sm in start_matches:
                if sm.group(1) == ts_str:
                    best_match = sm
                    break
            if not best_match and start_matches:
                try:
                    err_dt = datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                    best_diff = None
                    for sm in start_matches:
                        sm_dt = datetime.datetime.strptime(sm.group(1), "%Y-%m-%d %H:%M:%S")
                        if sm_dt <= err_dt:
                            diff = (err_dt - sm_dt).total_seconds()
                            if best_diff is None or diff < best_diff:
                                best_diff = diff
                                best_match = sm
                except:
                    pass
            if best_match:
                sm_idx = start_matches.index(best_match)
                st_start = best_match.end()
                st_end = start_matches[sm_idx+1].start() if sm_idx + 1 < len(start_matches) else len(stdout_content)
                stdout_chunk = stdout_content[st_start:st_end].strip()

        diag = triage_single_error(source, stdout_chunk, err_chunk)
        errors.append({
            "id": f"{source}-{ts_str.replace(' ', '_').replace(':', '_')}",
            "timestamp": ts_str,
            "source": source,
            "title": diag["title"],
            "explanation": diag["explanation"],
            "steps": diag["steps"]
        })
    return errors

def get_recent_errors_history():
    all_errors = parse_all_errors_from_logs("announcer") + parse_all_errors_from_logs("settlement")
    def parse_dt(x):
        try:
            return datetime.datetime.strptime(x["timestamp"], "%Y-%m-%d %H:%M:%S")
        except:
            return datetime.datetime.min
    all_errors.sort(key=parse_dt, reverse=True)
    acknowledged = load_acknowledged_errors()
    for err in all_errors:
        err["acknowledged"] = err["id"] in acknowledged
    return all_errors[:3]

def triage_logs(a_out, a_err, s_out, s_err):
    diagnosis = {
        "status": "info",
        "title": "Awaiting System Run",
        "explanation": "No active tasks have failed or succeeded yet in this monitoring session.",
        "steps": ["Click 'Start Table Setup' or 'Run Manual Settlement' to begin."]
    }

    a_start = parse_last_timestamp(a_out, "=== Execution Started:")
    a_error = parse_last_timestamp(a_err, "=== Error Occurred:")
    s_start = parse_last_timestamp(s_out, "=== Execution Started:")
    s_error = parse_last_timestamp(s_err, "=== Error Occurred:")

    a_failed = False
    if a_error:
        if not a_start or a_error >= a_start:
            a_failed = True
            
    s_failed = False
    if s_error:
        if not s_start or s_error >= s_start:
            s_failed = True

    if not a_failed and not s_failed:
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

    announcer_failed_last = True
    if a_failed and s_failed:
        if a_error and s_error and s_error > a_error:
            announcer_failed_last = False
    elif s_failed:
        announcer_failed_last = False

    if not announcer_failed_last:
        s_combined = (s_out + "\n" + s_err).lower()
        nickname_match = re.search(r"player with nickname '([^']+)' not found", s_combined)
        if nickname_match:
            nickname = nickname_match.group(1)
            return {
                "status": "error",
                "title": "Missing Player Payment Mapping",
                "explanation": f"The settlement engine failed because a player with the nickname '{nickname}' is not registered in your player database.",
                "steps": [
                    "Open your player database Google Sheet.",
                    f"Add a new row mapping nickname <span class='copyable-badge' onclick='copyTextToClipboard(\"{nickname}\")' title='Click to copy nickname'>{nickname} 📋</span> to their Venmo handle.",
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
                    f"Ensure that calendar_credentials.json is present in the root folder {WORKING_DIR}.",
                    "Verify the CALENDAR_ID in your .env file matches the shared calendar's settings."
                ]
            }

        return {
            "status": "error",
            "title": "Game Announcer Execution Crash",
            "explanation": "The table creation task encountered an unexpected Python exception.",
            "steps": [
                "Review the Announcer Errors log below for the full traceback.",
                "Verify that schedule.json has correct syntax and formats."
            ]
        }

class LocalAgentHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def check_token(self):
        req_token = self.headers.get("X-Agent-Token")
        if not req_token:
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            if "token" in query:
                req_token = query["token"][0]
        
        if not req_token or req_token != AGENT_TOKEN:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Unauthorized: Invalid or missing token"}).encode("utf-8"))
            return False
        return True

    def do_GET(self):
        if not self.check_token():
            return

        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path

        if path == "/api/status":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            
            last_games = {}
            games_json_path = os.path.join(WORKING_DIR, "last_created_games.json")
            if os.path.exists(games_json_path):
                try:
                    with open(games_json_path, "r") as f:
                        last_games = json.load(f)
                except:
                    pass

            pending_email = {}
            pending_email_path = os.path.join(WORKING_DIR, "pending_email.json")
            if os.path.exists(pending_email_path):
                try:
                    with open(pending_email_path, "r") as f:
                        draft_data = json.load(f)
                        pending_email = {
                            "has_draft": True,
                            "subject": draft_data.get("subject"),
                            "body": draft_data.get("body"),
                            "type": draft_data.get("type")
                        }
                except:
                    pass

            with status_lock:
                a_stdout = get_last_log_lines(os.path.join(WORKING_DIR, "output/game_nights_stdout.log"))
                a_stderr = get_last_log_lines(os.path.join(WORKING_DIR, "output/game_nights_stderr.log"))
                s_stdout = get_last_log_lines(os.path.join(WORKING_DIR, "output/next_morning_stdout.log"))
                s_stderr = get_last_log_lines(os.path.join(WORKING_DIR, "output/next_morning_stderr.log"))
                
                diagnosis = triage_logs(a_stdout, a_stderr, s_stdout, s_stderr)
                
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

                diag_ts = None
                if diagnosis.get("status") == "success":
                    if "settlement" in diagnosis.get("title", "").lower():
                        diag_ts = s_start
                    else:
                        diag_ts = a_start
                elif diagnosis.get("status") == "error":
                    diag_ts = a_error if a_err_current else (s_error if s_err_current else (a_error or s_error))
                
                diagnosis["timestamp"] = diag_ts.strftime("%Y-%m-%d %H:%M:%S") if diag_ts else None

                active_id = None
                if diagnosis.get("status") == "error" and diagnosis.get("timestamp"):
                    source_str = "announcer" if (a_err_current or (a_error and not s_error) or (a_error and s_error and a_error > s_error)) else "settlement"
                    ts_normalized = diagnosis["timestamp"].replace(" ", "_").replace(":", "_")
                    active_id = f"{source_str}-{ts_normalized}"
                
                acknowledged = load_acknowledged_errors()
                diagnosis["id"] = active_id
                diagnosis["acknowledged"] = (active_id in acknowledged) if active_id else False

                skip_schedule_tonight = False
                skip_path = os.path.join(WORKING_DIR, "skip_schedule.txt")
                if os.path.exists(skip_path):
                    try:
                        with open(skip_path, "r") as f:
                            skip_date = f.read().strip()
                        if skip_date == datetime.datetime.now().strftime("%Y-%m-%d"):
                            skip_schedule_tonight = True
                    except:
                        pass

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
                    "server_time": datetime.datetime.now().strftime("%A, %b %d, %Y - %I:%M:%S %p"),
                    "pending_email": pending_email,
                    "errors_history": get_recent_errors_history(),
                    "skip_schedule_tonight": skip_schedule_tonight
                }
            self.wfile.write(json.dumps(status).encode("utf-8"))
            
        elif path == "/api/execution-times":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            
            import plistlib
            def get_hour_minute(plist_name, default_hour):
                path = os.path.expanduser(f"~/Library/LaunchAgents/{plist_name}")
                if os.path.exists(path):
                    try:
                        with open(path, 'rb') as f:
                            pl = plistlib.load(f)
                            intervals = pl.get("StartCalendarInterval", [])
                            if intervals and len(intervals) > 0:
                                h = intervals[0].get("Hour", default_hour)
                                m = intervals[0].get("Minute", 0)
                                return f"{h:02d}:{m:02d}"
                    except Exception as e:
                        print(f"[Agent] Error reading {plist_name}: {e}")
                return f"{default_hour:02d}:00"
                
            game_nights_time = get_hour_minute("com.pokernow.game_nights.plist", 17)
            next_morning_time = get_hour_minute("com.pokernow.next_morning.plist", 8)
            
            self.wfile.write(json.dumps({
                "setup_time": game_nights_time,
                "settlement_time": next_morning_time
            }).encode("utf-8"))
            
        elif path == "/api/schedule":
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
                    print(f"[Agent] Error reading schedule.json: {e}")
            self.wfile.write(json.dumps(schedule_data).encode("utf-8"))
        elif path == "/api/activity-logs":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            activity_file = os.path.join(WORKING_DIR, "output", "admin_activity.json")
            logs = []
            if os.path.exists(activity_file):
                try:
                    with open(activity_file, "r") as f:
                        logs = json.load(f)
                except Exception as e:
                    print(f"[Agent] Error reading admin_activity.json: {e}")
            self.wfile.write(json.dumps({"logs": logs}).encode("utf-8"))
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        if not self.check_token():
            return

        admin_email = self.headers.get("X-Admin-Email")
        admin_ip = self.headers.get("X-Admin-IP")

        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path

        if path == "/api/send-otp-email":
            content_length = int(self.headers.get('Content-Length', 0))
            success = False
            error_msg = ""
            if content_length > 0:
                try:
                    post_data = self.rfile.read(content_length)
                    payload = json.loads(post_data.decode("utf-8"))
                    receiver = payload.get("email")
                    otp_code = payload.get("otp")
                    
                    # Fetch SMTP details from env loaded from .env
                    sender = os.environ.get("EMAIL_SENDER")
                    password = os.environ.get("EMAIL_PASSWORD")
                    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
                    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
                    
                    if receiver and otp_code and sender and password:
                        subject = "LCR Poker Admin - One-Time Verification Code"
                        body = f"""
                        Hello,

                        Your one-time verification code to access the Poker Now Control Panel is:

                        ===========================
                                 {otp_code}
                        ===========================

                        This code is valid for the next 10 minutes. If you did not request this login, please ignore this email.

                        Best regards,
                        LCR Poker Admins
                        """
                        msg = MIMEText(body)
                        msg["Subject"] = subject
                        msg["From"] = f"LCR Admins <{sender}>"
                        msg["To"] = receiver
                        
                        try:
                            if smtp_port == 465:
                                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10)
                            else:
                                server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
                                server.starttls()
                            server.login(sender, password)
                            server.sendmail(sender, [receiver], msg.as_string())
                            server.quit()
                            print(f"[Agent] Successfully sent OTP email to {receiver} on behalf of Cloud UI")
                            success = True
                        except Exception as e:
                            import traceback
                            error_msg = f"SMTP error: {e}"
                            print(f"[Agent] SMTP failure: {error_msg}")
                            print(traceback.format_exc())
                    else:
                        error_msg = "Missing fields or SMTP credentials in .env on Mac Mini"
                except Exception as e:
                    error_msg = f"Request parsing error: {e}"
                    print(f"[Agent] Error sending OTP: {error_msg}")
            
            self.send_response(200 if success else 400)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success, "error": error_msg}).encode("utf-8"))
            return

        elif path == "/api/run-announcer":
            content_length = int(self.headers.get('Content-Length', 0))
            cmd = [sys.executable, "announce_games.py"]
            test_flag = False
            draft_flag = False
            if content_length > 0:
                try:
                    post_data = self.rfile.read(content_length)
                    payload = json.loads(post_data.decode("utf-8"))
                    test_flag = payload.get("test", False)
                    draft_flag = payload.get("draft", False)
                    if test_flag:
                        cmd += ["--test"]
                    if draft_flag:
                        cmd += ["--draft"]
                except Exception as e:
                    print(f"[Agent] Error parsing run-announcer payload: {e}")
            success = run_script_in_background("announcer", cmd)
            if success and admin_email:
                log_admin_activity(admin_email, "Ran Announcer", f"test={test_flag}, draft={draft_flag}", admin_ip)
            self.send_response(200 if success else 409)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success}).encode("utf-8"))
            
        elif path == "/api/run-settlement":
            content_length = int(self.headers.get('Content-Length', 0))
            cmd = [sys.executable, "auto_settle.py"]
            if content_length > 0:
                try:
                    post_data = self.rfile.read(content_length)
                    payload = json.loads(post_data.decode("utf-8"))
                    desc = payload.get("description", "").strip()
                    gids = payload.get("game_ids", [])
                    is_test = payload.get("test", False)
                    is_draft = payload.get("draft", False)
                    if desc:
                        cmd += ["--description", desc]
                    if gids:
                        cmd += ["--game_ids"] + gids
                    if is_test:
                        cmd += ["--no-email"]
                    if is_draft:
                        cmd += ["--draft"]
                except Exception as e:
                    print(f"[Agent] Error parsing run-settlement payload: {e}")
            else:
                cmd += ["--force"]

            success = run_script_in_background("settlement", cmd)
            if success and admin_email:
                log_admin_activity(admin_email, "Ran Settlement", f"test={is_test}, draft={is_draft}", admin_ip)
            self.send_response(200 if success else 409)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success}).encode("utf-8"))
            
        elif path == "/api/schedule":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                new_schedule = json.loads(post_data.decode("utf-8"))
                schedule_path = os.path.join(WORKING_DIR, "schedule.json")
                with open(schedule_path, "w") as f:
                    json.dump(new_schedule, f, indent=4)
                
                if admin_email:
                    log_admin_activity(admin_email, "Updated Schedule", "", admin_ip)
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
                
                def _post_save():
                    try:
                        subprocess.run([sys.executable, "setup_local_scheduler.py", "--skip-web-ui"], cwd=WORKING_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    except Exception as ex:
                        print(f"[Agent] Error reloading scheduler: {ex}")
                    try:
                        subprocess.run(["./sync_to_drive.sh"], cwd=WORKING_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    except Exception:
                        pass
                t = threading.Thread(target=_post_save, daemon=True)
                t.start()
                return
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
                
        elif path == "/api/run-adhoc":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                payload = json.loads(post_data.decode("utf-8"))
                if isinstance(payload, dict) and "config" in payload:
                    success = False
                    # trigger run-adhoc
                    # logic remains same, let's keep success tracking...
                    # we will wrap success logic and then log_admin_activity(admin_email, "Ran Ad-hoc Session", "", admin_ip)
                    adhoc_config = payload["config"]
                    is_draft = payload.get("draft", False)
                else:
                    adhoc_config = payload
                    is_draft = False
                config_str = json.dumps(adhoc_config)
                cmd = [sys.executable, "announce_games.py", "--config", config_str, "--adhoc"]
                if is_draft:
                    cmd += ["--draft"]
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
                
        elif path == "/api/approve-email":
            task_type = "announcer"
            pending_email_path = os.path.join(WORKING_DIR, "pending_email.json")
            if os.path.exists(pending_email_path):
                try:
                    with open(pending_email_path, "r") as f:
                        draft_data = json.load(f)
                        if draft_data.get("type") == "settlement":
                            task_type = "settlement"
                except:
                    pass
            cmd = [sys.executable, "send_pending_email.py"]
            success = run_script_in_background(task_type, cmd)
            self.send_response(200 if success else 409)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success}).encode("utf-8"))
            
        elif path == "/api/discard-email":
            pending_email_path = os.path.join(WORKING_DIR, "pending_email.json")
            success = False
            if os.path.exists(pending_email_path):
                try:
                    os.remove(pending_email_path)
                    subprocess.run(["./sync_to_drive.sh"], cwd=WORKING_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    success = True
                except Exception as e:
                    print(f"[Agent] Error deleting draft: {e}")
            self.send_response(200 if success else 500)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success}).encode("utf-8"))
            
        elif path == "/api/kill-task":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            success = False
            try:
                payload = json.loads(post_data.decode("utf-8"))
                task_name = payload.get("task")
                if task_name in ["announcer", "settlement"]:
                    script_name = "announce_games.py" if task_name == "announcer" else "auto_settle.py"
                    subprocess.run(["pkill", "-f", script_name])
                    subprocess.run(["pkill", "-f", "chrome-profile"])
                    
                    with status_lock:
                        running_tasks[task_name] = False
                    success = True
            except Exception as e:
                print(f"[Agent] Error killing task: {e}")
            self.send_response(200 if success else 400)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success}).encode("utf-8"))
            
        elif path == "/api/acknowledge-error":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            success = False
            try:
                payload = json.loads(post_data.decode("utf-8"))
                error_id = payload.get("id")
                if error_id:
                    success = save_acknowledged_error(error_id)
            except Exception as e:
                print(f"[Agent] Error acknowledging error: {e}")
            self.send_response(200 if success else 400)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success}).encode("utf-8"))
            
        elif path == "/api/execution-times":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            success = False
            try:
                payload = json.loads(post_data.decode("utf-8"))
                setup_time = payload.get("setup_time")
                settlement_time = payload.get("settlement_time")
                
                import plistlib
                def set_hour_minute(plist_name, time_str):
                    if not time_str: return
                    path = os.path.expanduser(f"~/Library/LaunchAgents/{plist_name}")
                    if os.path.exists(path):
                        h, m = map(int, time_str.split(':'))
                        with open(path, 'rb') as f:
                            pl = plistlib.load(f)
                        intervals = pl.get("StartCalendarInterval", [])
                        for i in intervals:
                            i["Hour"] = h
                            i["Minute"] = m
                        with open(path, 'wb') as f:
                            plistlib.dump(pl, f)
                        
                        subprocess.run(["launchctl", "unload", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        subprocess.run(["launchctl", "load", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                if setup_time:
                    set_hour_minute("com.pokernow.game_nights.plist", setup_time)
                if settlement_time:
                    set_hour_minute("com.pokernow.next_morning.plist", settlement_time)
                
                success = True
            except Exception as e:
                print(f"[Agent] Error saving execution times: {e}")
                
            self.send_response(200 if success else 400)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success}).encode("utf-8"))
            
        elif path == "/api/toggle-skip-schedule":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            success = False
            try:
                payload = json.loads(post_data.decode("utf-8"))
                skip_it = payload.get("skip", False)
                skip_path = os.path.join(WORKING_DIR, "skip_schedule.txt")
                if skip_it:
                    with open(skip_path, "w") as f:
                        f.write(datetime.datetime.now().strftime("%Y-%m-%d"))
                else:
                    if os.path.exists(skip_path):
                        os.remove(skip_path)
                success = True
            except Exception as e:
                print(f"[Agent] Error toggling skip schedule: {e}")
            self.send_response(200 if success else 400)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success}).encode("utf-8"))
        elif path == "/api/log-activity":
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                try:
                    post_data = self.rfile.read(content_length)
                    payload = json.loads(post_data.decode("utf-8"))
                    email = payload.get("email")
                    action = payload.get("action")
                    details = payload.get("details", "")
                    ip = payload.get("ip", "")
                    log_admin_activity(email, action, details, ip)
                except Exception as e:
                    print(f"[Agent] Error logging activity: {e}")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
            return
        else:
            self.send_error(404, "Not Found")

def run(server_class=HTTPServer, handler_class=LocalAgentHandler):
    server_address = ('', PORT)
    httpd = server_class(server_address, handler_class)
    print(f"[Agent] Headless agent server started on port {PORT}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()

if __name__ == '__main__':
    run()
