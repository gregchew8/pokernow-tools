#!/usr/bin/env python3
import os
import sys
import json
import smtplib
import subprocess
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

def send_email(subject, html_content):
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    sender = os.environ.get("EMAIL_SENDER")
    password = os.environ.get("EMAIL_PASSWORD")
    receiver = os.environ.get("EMAIL_RECEIVER")

    if not all([sender, password, receiver]):
        print("Skipping email settlement: EMAIL_SENDER, EMAIL_PASSWORD, or EMAIL_RECEIVER not set in environment.")
        return False

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = receiver

    # Use HTML content directly since pokernow_settlement produces rich HTML
    part = MIMEText(html_content, 'html')
    msg.attach(part)

    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
            
        server.login(sender, password)
        server.sendmail(sender, receiver, msg.as_string())
        server.quit()
        print(f"Settlement email sent successfully to {receiver}")
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def post_to_discord(subject, html_content):
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        return False

    import requests
    # HTML doesn't look good directly on Discord, so let's strip HTML tags or format simply
    # For Discord, we can parse the HTML lines and extract the pre block text if possible
    text_content = html_content
    if "<pre>" in html_content and "</pre>" in html_content:
        pre_content = html_content.split("<pre>")[1].split("</pre>")[0]
        # Clean HTML links for markdown
        import re
        # Convert <a href="...">name</a> to [name](href)
        pre_content = re.sub(r'<a href="([^"]+)">([^<]+)</a>', r'[\2](\1)', pre_content)
        text_content = f"**{subject}**\n\n```\n{pre_content}\n```"
    else:
        text_content = f"**{subject}**\n\n{text_content}"

    payload = {
        "content": text_content
    }
    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        print("Discord settlement posted successfully.")
        return True
    except Exception as e:
        print(f"Error posting settlement to Discord: {e}")
        return False

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

def sync_to_google_drive():
    drive_path = "/Users/gregchew/Library/CloudStorage/GoogleDrive-gregchew@gmail.com/My Drive/pokernow"
    if not os.path.exists(drive_path):
        print(f"Skipping Google Drive backup: path {drive_path} does not exist.")
        return
    
    print("\nBacking up files to Google Drive...")
    src = "/Users/gregchew/pokernow/"
    cmd = [
        "rsync", "-av", "--delete",
        "--exclude=chrome-profile",
        "--exclude=.git",
        src,
        drive_path + "/"
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("Backup to Google Drive completed successfully.")
    except Exception as e:
        print(f"Warning: Failed to back up files to Google Drive: {e}")

def main():
    import datetime
    print(f"\n=== Execution Started: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    load_env()
    # 1. Sync player mapping first
    print("Step 1: Syncing player database...")
    subprocess.run([sys.executable, "sync_players.py"], check=True)

    # 2. Load the last created game details
    if not os.path.exists("last_created_games.json"):
        print("Error: last_created_games.json does not exist. No games recorded for settlement.")
        sys.exit(1)

    with open("last_created_games.json", "r") as f:
        game_history = json.load(f)

    # Prevent reconciling outdated games (e.g. if the previous night's game run failed)
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    game_date = game_history.get("date")
    if game_date != yesterday and "--force" not in sys.argv:
        print(f"Skipping settlement: Last created game date ({game_date}) does not match yesterday's date ({yesterday}).")
        print("To force settlement of older games, run with: python3 auto_settle.py --force")
        return

    import datetime
    game_ids = game_history.get("game_ids", [])
    description = game_history.get("description", "")
    
    if not game_ids:
        print("Error: No game IDs found in last_created_games.json.")
        sys.exit(1)

    print(f"Step 2: Calculating settlement for games: {game_ids} with desc {description}")
    
    settle_cmd = [
        sys.executable,
        "pokernow_settlement.py",
        "--description", description,
        "--game_ids"
    ] + game_ids

    # Run the settlement script
    result = subprocess.run(settle_cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if result.returncode != 0:
        error_details = result.stderr.strip() if result.stderr else result.stdout.strip()
        raise RuntimeError(f"Settlement calculation failed. pokernow_settlement.py exited with code {result.returncode}.\n\nSubprocess Output:\n{error_details}")

    # 3. Read generated HTML report
    report_file = f"./output/settlement_{description}.html"
    if not os.path.exists(report_file):
        report_file = "./output/settlement.html"
        if not os.path.exists(report_file):
            raise FileNotFoundError("Error: Settlement report file not found in ./output/")

    with open(report_file, "r", encoding="utf-8") as f:
        report_html = f.read()

    subject = f"Poker Settlement Payouts - {description}"
    
    # 4. Email/Discord the report
    send_email(subject, report_html)
    post_to_discord(subject, report_html)
    
    # Automatically backup outputs to Google Drive
    sync_to_google_drive()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        import datetime
        error_msg = traceback.format_exc()
        print(f"\n=== Error Occurred: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===", file=sys.stderr)
        print(error_msg, file=sys.stderr)
        
        load_env()
        sync_to_google_drive()
        
        admin_email = os.environ.get("EMAIL_SENDER")
        if admin_email:
            subject = f"ALERT: Poker Settlement Failed ({datetime.datetime.now().strftime('%Y-%m-%d')})"
            html_content = f"<h3>Poker Settlement Failed</h3><p>The morning settlement task encountered an error:</p><pre style='color: red; padding: 10px; background: #f9f9f9; border: 1px solid #ccc;'>{error_msg}</pre>"
            
            original_receiver = os.environ.get("EMAIL_RECEIVER")
            os.environ["EMAIL_RECEIVER"] = admin_email
            send_email(subject, html_content)
            if original_receiver:
                os.environ["EMAIL_RECEIVER"] = original_receiver
        sys.exit(1)
