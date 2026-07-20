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
AGENT_TOKEN = os.environ.get("AGENT_TOKEN", "").strip()
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
        "Content-Type": "application/json"
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
        
        # Extend session lifetime (sliding window of 7 days)
        session["expires"] = time.time() + (7 * 24 * 3600)
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

        # Forward the path and query string exactly to the agent
        target_url = f"{AGENT_URL}{self.path}"
        headers = {
            "X-Agent-Token": AGENT_TOKEN,
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
            self.wfile.write(dashboard_html.encode("utf-8"))
            
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
                "expires": time.time() + (7 * 24 * 3600)  # 7 days session
            }

            self.send_response(303)
            self.send_header("Set-Cookie", f"session_id={session_id}; Path=/; Max-Age={7 * 24 * 3600}; HttpOnly; SameSite=Lax")
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
