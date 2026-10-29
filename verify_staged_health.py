#!/usr/bin/env python3
"""
verify_staged_health.py
Automated background health monitor for multi-day staged Poker Now tables.
Verifies all staged game rooms 2x daily (10:00 AM & 3:30 PM).
If any table has expired, redirected, or exceeded max safe age, alerts Greg via email & Discord.
"""

import os
import sys
import json
import time
import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

WORKING_DIR = os.path.dirname(os.path.abspath(__file__))

def load_env():
    env_file = os.path.join(WORKING_DIR, ".env")
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        k, v = line.split("=", 1)
                        os.environ[k.strip()] = v.strip().strip('"').strip("'")

load_env()

def log_activity(action, details=""):
    activity_file = os.path.join(WORKING_DIR, "output", "admin_activity.json")
    try:
        logs = []
        if os.path.exists(activity_file):
            with open(activity_file, "r") as f:
                logs = json.load(f)
        logs.insert(0, {
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "email": "Health Monitor (System)",
            "action": action,
            "details": details,
            "ip": "127.0.0.1"
        })
        with open(activity_file, "w") as f:
            json.dump(logs[:500], f, indent=2)
    except Exception as e:
        print(f"[HealthMonitor] Error logging activity: {e}", file=sys.stderr)

def send_alert_email(subject, html_content, text_content):
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    sender = os.environ.get("EMAIL_SENDER")
    password = os.environ.get("EMAIL_PASSWORD")
    recipient = "gregchew@gmail.com"
    email_from = os.environ.get("EMAIL_FROM", f"LCR Health Monitor <{sender}>")

    if not sender or not password:
        print("[HealthMonitor] Cannot send email alert: EMAIL_SENDER or EMAIL_PASSWORD missing.", file=sys.stderr)
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email_from
    msg["To"] = recipient

    msg.attach(MIMEText(text_content, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
        server.login(sender, password)
        server.sendmail(sender, [recipient], msg.as_string())
        server.quit()
        print(f"[HealthMonitor] Alert email sent successfully to {recipient}")
        return True
    except Exception as e:
        print(f"[HealthMonitor] Failed to send alert email: {e}", file=sys.stderr)
        return False

def send_discord_alert(content):
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url or webhook_url.endswith("..."):
        return False
    try:
        import urllib.request
        payload = json.dumps({"content": content}).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 204)
    except Exception as e:
        print(f"[HealthMonitor] Discord alert failed: {e}", file=sys.stderr)
        return False

def run_health_check(force_alert=False):
    import stage_manager
    staged = stage_manager.load_staged_games()
    now_str = datetime.datetime.now().strftime("%A, %b %d %I:%M %p")
    
    if not staged:
        print(f"[HealthMonitor] [{now_str}] No staged games found in queue. Nothing to verify.")
        return 0

    total_tables = 0
    issues = []
    summary_report = []

    print(f"[HealthMonitor] [{now_str}] Running automated health verification on {len(staged)} staged day(s)...")

    for day_idx, date_str in enumerate(sorted(staged.keys())):
        if day_idx > 0:
            time.sleep(3.0)  # 3.0s pacing between day batches
        entry = staged[date_str]
        day_name = entry.get("day", "").upper()
        res = stage_manager.verify_staged_batch_health(date_str, run_http_probe=True)
        table_results = res.get("tables", [])
        total_tables += len(table_results)

        for t in table_results:
            is_healthy = t.get("healthy", False)
            table_info = {
                "date": date_str,
                "day": day_name,
                "table_num": t.get("table_num"),
                "game_type": (t.get("game_type") or "").upper(),
                "game_id": t.get("game_id"),
                "healthy": is_healthy,
                "reason": t.get("reason", "Unknown")
            }
            summary_report.append(table_info)
            if not is_healthy:
                issues.append(table_info)

    if force_alert and not issues:
        issues.append({
            "date": "2026-10-30",
            "day": "FRIDAY",
            "table_num": 1,
            "game_type": "NLH",
            "game_id": "pglTEST_ALERT_ONLY",
            "healthy": False,
            "reason": "Simulated Alert: Room expired check"
        })

    if issues:
        print(f"[HealthMonitor] ⚠️ ISSUES DETECTED: {len(issues)} table(s) unhealthy out of {total_tables} staged tables!", file=sys.stderr)
        
        # Build HTML table for email
        rows_html = ""
        for item in summary_report:
            status_icon = "🟢 OK" if item["healthy"] else "🔴 FAILED"
            status_color = "#10b981" if item["healthy"] else "#ef4444"
            rows_html += f"""
            <tr style="border-bottom: 1px solid #e2e8f0;">
                <td style="padding: 10px; font-weight: 600;">{item['day']} ({item['date']})</td>
                <td style="padding: 10px;">Table {item['table_num']} ({item['game_type']})</td>
                <td style="padding: 10px;"><a href="https://www.pokernow.com/games/{item['game_id']}" style="color: #4f46e5; text-decoration: none;">{item['game_id']}</a></td>
                <td style="padding: 10px; color: {status_color}; font-weight: bold;">{status_icon}</td>
                <td style="padding: 10px; font-size: 13px; color: #64748b;">{item['reason']}</td>
            </tr>
            """

        subject = f"⚠️ [LCR Poker Alert] Staged Table Issue Detected ({len(issues)} table{'s' if len(issues) > 1 else ''})"
        
        html_content = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 650px; margin: 0 auto; color: #1e293b; line-height: 1.5;">
            <div style="background: #ef4444; color: white; padding: 18px 24px; border-radius: 8px 8px 0 0;">
                <h2 style="margin: 0; font-size: 20px;">⚠️ Staged Poker Table Issue Detected</h2>
                <p style="margin: 4px 0 0 0; opacity: 0.9; font-size: 14px;">Automated 2x-daily health probe encountered issues with upcoming staged games.</p>
            </div>
            
            <div style="padding: 24px; border: 1px solid #e2e8f0; border-top: none; border-radius: 0 0 8px 8px; background: #ffffff;">
                <p>Hello Greg,</p>
                <p>During the automated health check at <strong>{now_str}</strong>, the system probed your upcoming staged tables and detected <strong>{len(issues)} table issue(s)</strong> that require attention before game night:</p>
                
                <table style="width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 14px; text-align: left;">
                    <thead>
                        <tr style="background: #f8fafc; border-bottom: 2px solid #cbd5e1; color: #475569;">
                            <th style="padding: 10px;">Game Night</th>
                            <th style="padding: 10px;">Table</th>
                            <th style="padding: 10px;">Poker Now ID</th>
                            <th style="padding: 10px;">Status</th>
                            <th style="padding: 10px;">Diagnostics</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
                
                <div style="background: #f0fdf4; border: 1px solid #86efac; border-radius: 6px; padding: 16px; margin: 20px 0;">
                    <h3 style="margin: 0 0 8px 0; color: #166534; font-size: 15px;">🛠️ Recommended Recovery Steps:</h3>
                    <ol style="margin: 0; padding-left: 20px; color: #14532d; font-size: 14px;">
                        <li style="margin-bottom: 6px;">Open the <strong><a href="https://poker.gchew.com" style="color: #15803d; font-weight: bold;">LCR Poker Admin Portal</a></strong>.</li>
                        <li style="margin-bottom: 6px;">Under the <strong>Staged Games Queue</strong>, find the affected date.</li>
                        <li style="margin-bottom: 6px;">Click <strong>Regenerate</strong> for that day to re-create fresh tables in a single session.</li>
                        <li>The system will automatically announce the fresh tables on game night as scheduled.</li>
                    </ol>
                </div>
                
                <p style="font-size: 12px; color: #94a3b8; margin-top: 30px; border-top: 1px solid #e2e8f0; padding-top: 15px;">
                    This is an automated safety alert from your Mac Mini Poker Now daemon.
                </p>
            </div>
        </div>
        """

        text_content = f"LCR Poker Alert: Staged Table Issue Detected\n\nIssues found during health check ({now_str}):\n"
        for i in issues:
            text_content += f"- {i['day']} ({i['date']}) Table {i['table_num']}: {i['reason']} (https://www.pokernow.com/games/{i['game_id']})\n"
        text_content += "\nAction: Open https://poker.gchew.com and click 'Regenerate' for the affected day."

        # Send Email Alert
        send_alert_email(subject, html_content, text_content)

        # Send Discord Alert
        discord_msg = f"⚠️ **[Poker Alert] Staged Table Issue Detected!**\nHealth probe at {now_str} found {len(issues)} unhealthy table(s):\n"
        for i in issues[:4]:
            discord_msg += f"• **{i['day']} ({i['date']}) Table {i['table_num']}**: {i['reason']}\n"
        discord_msg += "👉 Please visit https://poker.gchew.com to regenerate."
        send_discord_alert(discord_msg)

        # Log Activity
        issue_summary = ", ".join([f"{i['day']} T{i['table_num']} ({i['reason']})" for i in issues[:3]])
        log_activity("Staged Health Alert", f"{len(issues)} issue(s) detected: {issue_summary}")
        return 1
    else:
        print(f"[HealthMonitor] ✅ [{now_str}] Health check passed: All {total_tables} staged tables across {len(staged)} day(s) are active and verified.")
        log_activity("Staged Health Check", f"Verified {total_tables} table(s) across {len(staged)} day(s) - all active and healthy")
        return 0

if __name__ == "__main__":
    force = "--force-alert" in sys.argv
    exit_code = run_health_check(force_alert=force)
    sys.exit(exit_code)
