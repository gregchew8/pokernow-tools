#!/usr/bin/env python3
import os
import sys
import json
import secrets
import time
import datetime
import urllib.parse
import urllib.request
import smtplib
from email.mime.text import MIMEText
from http.server import BaseHTTPRequestHandler, HTTPServer
from http.cookies import SimpleCookie

# Reuse the HTML dashboard from the local web_ui.py to keep code DRY
from web_ui import WebUIHandler

PORT = int(os.environ.get("PORT", 8080))
WORKING_DIR = os.path.dirname(os.path.abspath(__file__))

# Load local environment variables from .env if present (useful for local dev/testing)
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

# Configuration
ALLOWED_EMAILS = [email.strip().lower() for email in os.environ.get("ALLOWED_EMAILS", "").split(",") if email.strip()]
AGENT_URL = os.environ.get("AGENT_URL", "").strip().rstrip("/")
AGENT_TOKEN = os.environ.get("AGENT_TOKEN", "").strip().strip('"').strip("'")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))

print(f"[CloudUI] Allowed emails: {ALLOWED_EMAILS}")
print(f"[CloudUI] Agent URL: {AGENT_URL}")

# In-memory stores
otp_store = {}        # email -> { "otp": str, "expires": float }
session_store = {}    # session_id -> { "email": str, "expires": float }

def send_otp_email(receiver_email, otp_code):
    import urllib.request
    import json
    import traceback
    
    print(f"[CloudUI] Delegating OTP email sending for {receiver_email} to Mac Mini local agent...")
    if not AGENT_URL or not AGENT_TOKEN:
        print("[CloudUI] Error: AGENT_URL or AGENT_TOKEN not configured. Cannot delegate email sending.")
        return False
        
    target_url = f"{AGENT_URL}/api/send-otp-email"
    headers = {
        "X-Agent-Token": AGENT_TOKEN,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    payload = {
        "email": receiver_email,
        "otp": otp_code
    }
    body_data = json.dumps(payload).encode("utf-8")
    
    req = urllib.request.Request(target_url, data=body_data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            if response.status == 200:
                resp_data = json.loads(response.read().decode("utf-8"))
                if resp_data.get("success"):
                    print(f"[CloudUI] Local agent successfully sent the OTP email to {receiver_email}.")
                    return True
                else:
                    print(f"[CloudUI] Local agent failed to send email: {resp_data.get('error')}")
            else:
                print(f"[CloudUI] Local agent returned status {response.status} when sending email.")
    except Exception as e:
        print(f"[CloudUI] Error connecting to local agent to send email: {e}")
        print(traceback.format_exc())
    return False

def log_activity_to_agent(email, action, details="", ip=""):
    import urllib.request
    import json
    if not AGENT_URL or not AGENT_TOKEN:
        return
    target_url = f"{AGENT_URL}/api/log-activity"
    headers = {
        "X-Agent-Token": AGENT_TOKEN,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    payload = {
        "email": email,
        "action": action,
        "details": details,
        "ip": ip
    }
    try:
        req = urllib.request.Request(target_url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=5) as response:
            pass
    except Exception as e:
        print(f"[CloudUI] Error logging activity to agent: {e}")

class CloudUIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # We can enable standard logs or keep it clean
        print(f"[CloudUI] {self.address_string()} - - [{self.log_date_time_string()}] {format % args}")

    def get_session_id(self):
        cookie_header = self.headers.get("Cookie")
        if cookie_header:
            cookie = SimpleCookie(cookie_header)
            if "session_id" in cookie:
                return cookie["session_id"].value
        return None

    def is_authenticated(self):
        session_id = self.get_session_id()
        if not session_id or session_id not in session_store:
            return False
        
        session = session_store[session_id]
        if time.time() > session["expires"]:
            # Session expired
            del session_store[session_id]
            return False
        
        return True

    def serve_login_page(self, email_requested=None, error_msg=None):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

        otp_step_class = "hidden" if not email_requested else ""
        email_step_class = "" if not email_requested else "hidden"
        email_val = email_requested or ""
        error_display = f'<div class="error-banner">{error_msg}</div>' if error_msg else ""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LCR Poker Admin - Login</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-color: #0b0f19;
            --card-bg: rgba(22, 28, 45, 0.85);
            --border-color: rgba(255, 255, 255, 0.08);
            --text-color: #e2e8f0;
            --text-muted: #94a3b8;
            --primary: #4f46e5;
            --primary-hover: #6366f1;
            --danger: #ef4444;
            --glow: 0 0 30px rgba(79, 70, 229, 0.2);
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg-color);
            background-image: 
                radial-gradient(at 0% 0%, rgba(31, 41, 55, 0.3) 0, transparent 50%),
                radial-gradient(at 50% 0%, rgba(79, 70, 229, 0.07) 0, transparent 50%);
            color: var(--text-color);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 1.5rem;
        }}

        .login-card {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 2.5rem;
            width: 100%;
            max-width: 440px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5), var(--glow);
            backdrop-filter: blur(12px);
            transition: all 0.3s ease;
        }}

        .logo-area {{
            text-align: center;
            margin-bottom: 2rem;
        }}

        .logo-area h1 {{
            font-size: 1.8rem;
            font-weight: 800;
            background: linear-gradient(135deg, #fff 0%, #a5b4fc 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }}

        .logo-area p {{
            font-size: 0.9rem;
            color: var(--text-muted);
        }}

        .form-group {{
            margin-bottom: 1.5rem;
        }}

        label {{
            display: block;
            font-size: 0.85rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            margin-bottom: 0.5rem;
        }}

        input[type="email"], input[type="text"] {{
            width: 100%;
            padding: 0.8rem 1rem;
            font-size: 1rem;
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            color: #fff;
            outline: none;
            transition: all 0.2s ease;
        }}

        input[type="email"]:focus, input[type="text"]:focus {{
            border-color: var(--primary-hover);
            box-shadow: 0 0 10px rgba(99, 102, 241, 0.3);
        }}

        .btn {{
            width: 100%;
            padding: 0.8rem;
            font-size: 1rem;
            font-weight: 600;
            color: #fff;
            background: linear-gradient(135deg, var(--primary) 0%, #312e81 100%);
            border: none;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s ease;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}

        .btn:hover {{
            background: linear-gradient(135deg, var(--primary-hover) 0%, var(--primary) 100%);
            transform: translateY(-1px);
        }}

        .error-banner {{
            background: rgba(239, 68, 68, 0.15);
            border: 1px solid rgba(239, 68, 68, 0.3);
            color: #fca5a5;
            padding: 0.8rem 1rem;
            border-radius: 8px;
            font-size: 0.9rem;
            margin-bottom: 1.5rem;
            text-align: center;
        }}

        .hidden {{
            display: none;
        }}

        .back-link {{
            display: inline-block;
            margin-top: 1rem;
            font-size: 0.85rem;
            color: var(--text-muted);
            text-decoration: none;
            transition: color 0.2s;
        }}

        .back-link:hover {{
            color: #fff;
        }}
    </style>
</head>
<body>
    <div class="login-card">
        <div class="logo-area">
            <h1>LCR Poker Admin</h1>
            <p>Control Panel Secure Login</p>
        </div>

        {error_display}

        <!-- STEP 1: Enter Email -->
        <form action="/request-otp" method="POST" class="{email_step_class}">
            <div class="form-group">
                <label for="email">Admin Email Address</label>
                <input type="email" id="email" name="email" required placeholder="name@example.com" value="{email_val}">
            </div>
            <button type="submit" class="btn">Send Verification Code</button>
        </form>

        <!-- STEP 2: Enter OTP -->
        <form action="/verify-otp" method="POST" class="{otp_step_class}">
            <input type="hidden" name="email" value="{email_val}">
            <div class="form-group">
                <label for="otp">One-Time Verification Code</label>
                <input type="text" id="otp" name="otp" required placeholder="6-digit code" autocomplete="one-time-code" maxlength="6" pattern="\\d{{6}}">
            </div>
            <button type="submit" class="btn">Verify & Sign In</button>
            <div style="text-align: center;">
                <a href="/login" class="back-link">← Try another email</a>
            </div>
        </form>
    </div>
</body>
</html>
"""
        self.wfile.write(html.encode("utf-8"))

    def proxy_to_agent(self, method="GET", body_data=None):
        if not AGENT_URL or not AGENT_TOKEN:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Bad Gateway: Mac Mini local agent not configured"}).encode("utf-8"))
            return

        session_id = self.get_session_id()
        email = ""
        if session_id and session_id in session_store:
            email = session_store[session_id].get("email", "")
        client_ip = self.headers.get("X-Forwarded-For") or self.client_address[0]

        # Forward the path and query string exactly to the agent
        target_url = f"{AGENT_URL}{self.path}"
        headers = {
            "X-Agent-Token": AGENT_TOKEN,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "X-Admin-Email": email,
            "X-Admin-IP": client_ip
        }
        if "Content-Type" in self.headers:
            headers["Content-Type"] = self.headers["Content-Type"]

        req = urllib.request.Request(target_url, data=body_data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                self.send_response(response.status)
                for header, val in response.getheaders():
                    # Strip standard connection/length headers to rewrite cleanly
                    if header.lower() not in ["content-length", "connection", "transfer-encoding"]:
                        self.send_header(header, val)
                
                resp_content = response.read()
                self.send_header("Content-Length", str(len(resp_content)))
                self.end_headers()
                self.wfile.write(resp_content)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            for header, val in e.headers.items():
                if header.lower() not in ["content-length", "connection", "transfer-encoding"]:
                    self.send_header(header, val)
            resp_content = e.read()
            self.send_header("Content-Length", str(len(resp_content)))
            self.end_headers()
            self.wfile.write(resp_content)
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"Bad Gateway: Failed to contact local agent: {e}"}).encode("utf-8"))

    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path

        if path == "/login":
            if self.is_authenticated():
                self.send_response(303)
                self.send_header("Location", "/")
                self.end_headers()
                return
            self.serve_login_page()
            return
            
        elif path == "/logout":
            session_id = self.get_session_id()
            if session_id in session_store:
                email = session_store[session_id].get("email")
                if email:
                    log_activity_to_agent(email, "Logout", "", self.headers.get("X-Forwarded-For") or self.client_address[0])
                del session_store[session_id]
            self.send_response(303)
            self.send_header("Set-Cookie", "session_id=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT; HttpOnly; SameSite=Lax")
            self.send_header("Location", "/login")
            self.end_headers()
            return

        # Secure all other routes
        if not self.is_authenticated():
            self.send_response(303)
            self.send_header("Location", "/login")
            self.end_headers()
            return

        if path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            # Serve the standard dashboard
            dashboard_html = WebUIHandler.get_html_dashboard(None)
            
            # Inject Admin activity logs card
            admin_logs_html = """
            <!-- Admin Logs Section -->
            <div class="card full-width">
                <h2>Admin Activity Logs</h2>
                <div style="max-height: 250px; overflow-y: auto; border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; background: rgba(15,23,42,0.4); padding: 10px;">
                    <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; font-family:'Outfit',sans-serif;">
                        <thead>
                            <tr style="border-bottom: 1px solid rgba(255,255,255,0.1); color: #94a3b8; font-weight: 600;">
                                <th style="padding: 8px;">Time</th>
                                <th style="padding: 8px;">Admin</th>
                                <th style="padding: 8px;">Action</th>
                                <th style="padding: 8px;">Details</th>
                                <th style="padding: 8px;">IP</th>
                            </tr>
                        </thead>
                        <tbody id="admin-activity-table-body">
                            <tr><td colspan="5" style="padding: 15px; text-align: center; color: #94a3b8;">Loading activity logs...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
            
            <script>
            function loadAdminActivityLogs() {
                fetch('/api/activity-logs')
                    .then(r => r.json())
                    .then(data => {
                        const tbody = document.getElementById('admin-activity-table-body');
                        if (!tbody) return;
                        tbody.innerHTML = '';
                        if (!data.logs || data.logs.length === 0) {
                            tbody.innerHTML = '<tr><td colspan="5" style="padding: 15px; text-align: center; color: #94a3b8;">No activity logged yet.</td></tr>';
                            return;
                        }
                        data.logs.forEach(log => {
                            const tr = document.createElement('tr');
                            tr.style.borderBottom = '1px solid rgba(255,255,255,0.05)';
                            tr.style.color = '#e2e8f0';
                            
                            const tdTime = document.createElement('td');
                            tdTime.style.padding = '8px';
                            tdTime.style.whiteSpace = 'nowrap';
                            tdTime.textContent = log.time;
                            
                            const tdAdmin = document.createElement('td');
                            tdAdmin.style.padding = '8px';
                            tdAdmin.style.color = '#a5b4fc';
                            tdAdmin.textContent = log.email;
                            
                            const tdAction = document.createElement('td');
                            tdAction.style.padding = '8px';
                            tdAction.style.fontWeight = '600';
                            if (log.action.includes('login') || log.action.includes('Login')) {
                                tdAction.style.color = '#34d399';
                            } else if (log.action.includes('logout') || log.action.includes('Logout')) {
                                tdAction.style.color = '#f87171';
                            } else {
                                tdAction.style.color = '#60a5fa';
                            }
                            tdAction.textContent = log.action;
                            
                            const tdDetails = document.createElement('td');
                            tdDetails.style.padding = '8px';
                            tdDetails.textContent = log.details || '-';
                            
                            const tdIp = document.createElement('td');
                            tdIp.style.padding = '8px';
                            tdIp.style.color = '#94a3b8';
                            tdIp.textContent = log.ip || '-';
                            
                            tr.appendChild(tdTime);
                            tr.appendChild(tdAdmin);
                            tr.appendChild(tdAction);
                            tr.appendChild(tdDetails);
                            tr.appendChild(tdIp);
                            tbody.appendChild(tr);
                        });
                    })
                    .catch(err => console.error("Error loading admin logs:", err));
            }
            setTimeout(loadAdminActivityLogs, 1000);
            setInterval(loadAdminActivityLogs, 10000);
            </script>
            """
            dashboard_html = dashboard_html.replace("<!-- Logs Section -->", admin_logs_html + "<!-- Logs Section -->")
            
            # Inject Session HUD, Renew button, Logout, and Active Sessions Box
            injected_html = """
            <div id="session-manager-widget" style="position:fixed; bottom:20px; right:20px; z-index:9999; font-family:'Outfit',sans-serif;">
                <div id="session-pill" style="display:flex; align-items:center; gap:10px; background:rgba(22, 28, 45, 0.9); border:1px solid rgba(255,255,255,0.08); padding:8px 16px; border-radius:30px; box-shadow:0 10px 25px rgba(0,0,0,0.3); backdrop-filter:blur(8px); cursor:pointer; color:#e2e8f0; font-size:13px; font-weight:600; transition:all 0.3s; user-select:none;">
                    <span id="session-countdown-text">Session: 30:00</span>
                    <button id="btn-renew-session" style="background:#4f46e5; border:none; color:white; padding:4px 10px; border-radius:20px; font-size:11px; font-weight:600; cursor:pointer; transition:all 0.2s; font-family:'Outfit',sans-serif;">Renew</button>
                    <button id="btn-logout" style="background:#ef4444; border:none; color:white; padding:4px 10px; border-radius:20px; font-size:11px; font-weight:600; cursor:pointer; transition:all 0.2s; font-family:'Outfit',sans-serif;">Logout</button>
                </div>
                <div id="session-details-card" style="display:none; margin-top:10px; background:rgba(22, 28, 45, 0.95); border:1px solid rgba(255,255,255,0.08); width:280px; padding:15px; border-radius:12px; box-shadow:0 15px 35px rgba(0,0,0,0.4); backdrop-filter:blur(12px); color:#e2e8f0;">
                    <h4 style="font-size:12px; text-transform:uppercase; color:#94a3b8; letter-spacing:0.05em; margin-bottom:10px; border-bottom:1px solid rgba(255,255,255,0.05); padding-bottom:5px; margin-top:0;">Active Admin Sessions</h4>
                    <div id="sessions-list" style="display:flex; flex-direction:column; gap:8px; max-height:150px; overflow-y:auto;">
                    </div>
                </div>
            </div>
            <script>
            (function() {
                let expiresTimestamp = Date.now() + 1800000;
                function updateSessionsList() {
                    fetch('/api/active-sessions')
                        .then(r => r.json())
                        .then(data => {
                            const list = document.getElementById('sessions-list');
                            list.innerHTML = '';
                            data.sessions.forEach(s => {
                                const diff = Math.max(0, Math.round(s.expires - Date.now()/1000));
                                const mins = Math.floor(diff/60);
                                const secs = diff%60;
                                const timeStr = mins + ":" + (secs < 10 ? "0" : "") + secs;
                                
                                const item = document.createElement('div');
                                item.style.display = 'flex';
                                item.style.justifyContent = 'space-between';
                                item.style.alignItems = 'center';
                                item.style.fontSize = '12px';
                                item.style.padding = '4px 0';
                                
                                const emailSpan = document.createElement('span');
                                emailSpan.textContent = s.email + (s.is_current ? ' (You)' : '');
                                emailSpan.style.fontWeight = s.is_current ? 'bold' : 'normal';
                                emailSpan.style.color = s.is_current ? '#a5b4fc' : '#e2e8f0';
                                
                                const expSpan = document.createElement('span');
                                expSpan.textContent = timeStr;
                                expSpan.style.color = '#94a3b8';
                                
                                item.appendChild(emailSpan);
                                item.appendChild(expSpan);
                                list.appendChild(item);
                                
                                if (s.is_current) {
                                    expiresTimestamp = s.expires * 1000;
                                }
                            });
                        });
                }
                function tick() {
                    const remaining = Math.max(0, Math.round((expiresTimestamp - Date.now()) / 1000));
                    const mins = Math.floor(remaining / 60);
                    const secs = remaining % 60;
                    document.getElementById('session-countdown-text').textContent = "Session: " + mins + ":" + (secs < 10 ? "0" : "") + secs;
                    
                    const pill = document.getElementById('session-pill');
                    if (remaining <= 300) {
                        pill.style.border = '1px solid #ef4444';
                        pill.style.boxShadow = '0 0 15px rgba(239, 68, 68, 0.2)';
                    } else {
                        pill.style.border = '1px solid rgba(255,255,255,0.08)';
                        pill.style.boxShadow = '0 10px 25px rgba(0,0,0,0.3)';
                    }
                    if (remaining <= 0) {
                        window.location.href = '/logout';
                        return;
                    }
                    setTimeout(tick, 1000);
                }
                document.getElementById('session-pill').addEventListener('click', function(e) {
                    if (e.target.tagName === 'BUTTON') return;
                    const card = document.getElementById('session-details-card');
                    card.style.display = card.style.display === 'none' ? 'block' : 'none';
                    if (card.style.display === 'block') {
                        updateSessionsList();
                    }
                });
                document.getElementById('btn-renew-session').addEventListener('click', function() {
                    fetch('/api/renew-session', { method: 'POST' })
                        .then(r => r.json())
                        .then(data => {
                            if (data.success) {
                                expiresTimestamp = data.expires * 1000;
                                updateSessionsList();
                            } else {
                                window.location.href = '/logout';
                            }
                        });
                });
                document.getElementById('btn-logout').addEventListener('click', function() {
                    window.location.href = '/logout';
                });
                updateSessionsList();
                tick();
                setInterval(() => {
                    const card = document.getElementById('session-details-card');
                    if (card.style.display === 'block') {
                        updateSessionsList();
                    }
                }, 5000);
            })();
            </script>
            """
            dashboard_html = dashboard_html.replace("</body>", injected_html + "</body>")
            self.wfile.write(dashboard_html.encode("utf-8"))
            
        elif path == "/api/active-sessions":
            # Clean expired sessions
            now = time.time()
            expired_keys = [k for k, v in session_store.items() if now > v["expires"]]
            for k in expired_keys:
                del session_store[k]
                
            current_session_id = self.get_session_id()
            sessions_list = []
            for sid, info in session_store.items():
                sessions_list.append({
                    "email": info["email"],
                    "expires": info["expires"],
                    "is_current": (sid == current_session_id)
                })
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"sessions": sessions_list}).encode("utf-8"))
            return
            
        elif path == "/analytics":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(WebUIHandler.get_html_analytics(None).encode("utf-8"))
            return
            
        elif path.startswith("/api/player-stats"):
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            try:
                from db_client import DBClient
                db = DBClient()
                
                query = urllib.parse.parse_qs(parsed_path.query)
                start_date = query.get("start_date", [None])[0]
                end_date = query.get("end_date", [None])[0]
                
                stats = db.get_player_stats(start_date, end_date)
                history = db.get_player_history(start_date, end_date)
                
                sessions_cursor = db.execute("SELECT ledger_date, filename FROM sessions ORDER BY ledger_date DESC")
                sessions = [{"date": str(r[0]), "filename": r[1]} if db.is_postgres else {"date": str(r["ledger_date"]), "filename": r["filename"]} for r in sessions_cursor.fetchall()]
                
                self.wfile.write(json.dumps({
                    "success": True,
                    "stats": stats,
                    "history": history,
                    "sessions": sessions,
                    "db_type": "Postgres" if db.is_postgres else f"SQLite (Fallback: {db.error_msg})"
                }).encode("utf-8"))
            except Exception as e:
                self.wfile.write(json.dumps({
                    "success": False,
                    "error": str(e)
                }).encode("utf-8"))
            return
            
        elif path.startswith("/api/delete-session"):
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            try:
                from db_client import DBClient
                db = DBClient()
                query = urllib.parse.parse_qs(parsed_path.query)
                date_str = query.get("date", [None])[0]
                if not date_str:
                    raise Exception("Missing date parameter")
                db.delete_session(date_str)
                self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
            except Exception as e:
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
            return
            
        elif path.startswith("/api/"):
            self.proxy_to_agent("GET")
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        if path == "/request-otp":
            params = urllib.parse.parse_qs(body.decode("utf-8"))
            email = params.get("email", [""])[0].strip().lower()
            
            if not email:
                self.serve_login_page(error_msg="Please provide a valid email address.")
                return
                
            if email not in ALLOWED_EMAILS:
                print(f"[CloudUI] Denied access request for unauthorized email: {email}")
                self.serve_login_page(error_msg="Access Denied: Email address not on the allowed list.")
                return

            # Generate 6-digit OTP
            otp_code = f"{secrets.randbelow(900000) + 100000}"
            otp_store[email] = {
                "otp": otp_code,
                "expires": time.time() + 600  # 10 minutes expiry
            }
            
            # Send OTP
            success = send_otp_email(email, otp_code)
            if success:
                self.serve_login_page(email_requested=email)
            else:
                self.serve_login_page(error_msg="Failed to send verification email. Please check server SMTP configuration.")
            return

        elif path == "/verify-otp":
            params = urllib.parse.parse_qs(body.decode("utf-8"))
            email = params.get("email", [""])[0].strip().lower()
            otp_input = params.get("otp", [""])[0].strip()

            if not email or email not in otp_store:
                self.serve_login_page(error_msg="Session invalid. Please start over.")
                return

            stored_otp = otp_store[email]
            if time.time() > stored_otp["expires"]:
                del otp_store[email]
                self.serve_login_page(email_requested=email, error_msg="Verification code expired. Please request a new one.")
                return

            if otp_input != stored_otp["otp"]:
                self.serve_login_page(email_requested=email, error_msg="Invalid verification code. Please try again.")
                return

            # Clear verified OTP
            del otp_store[email]

            # Generate session
            session_id = secrets.token_hex(32)
            session_store[session_id] = {
                "email": email,
                "expires": time.time() + 1800  # 30 minutes session
            }
            log_activity_to_agent(email, "Login", "", self.headers.get("X-Forwarded-For") or self.client_address[0])

            self.send_response(303)
            self.send_header("Set-Cookie", f"session_id={session_id}; Path=/; Max-Age=1800; HttpOnly; SameSite=Lax")
            self.send_header("Location", "/")
            self.end_headers()
            return

        # Secure all other routes
        if not self.is_authenticated():
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Unauthorized"}).encode("utf-8"))
            return

        if path == "/api/renew-session":
            session_id = self.get_session_id()
            if session_id in session_store:
                session_store[session_id]["expires"] = time.time() + 1800 # 30 mins
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Set-Cookie", f"session_id={session_id}; Path=/; Max-Age=1800; HttpOnly; SameSite=Lax")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "expires": session_store[session_id]["expires"]}).encode("utf-8"))
            else:
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": "Unauthorized"}).encode("utf-8"))
            return

        if path.startswith("/api/"):
            self.proxy_to_agent("POST", body)
        else:
            self.send_error(404, "Not Found")

def run(server_class=HTTPServer, handler_class=CloudUIHandler):
    server_address = ('', PORT)
    httpd = server_class(server_address, handler_class)
    print(f"[CloudUI] Server running at http://localhost:{PORT}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()

if __name__ == '__main__':
    run()
