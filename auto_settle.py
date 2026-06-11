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

def main():
    # 1. Sync player mapping first
    print("Step 1: Syncing player database...")
    subprocess.run([sys.executable, "sync_players.py"], check=True)

    # 2. Load the last created game details
    if not os.path.exists("last_created_games.json"):
        print("Error: last_created_games.json does not exist. No games recorded for settlement.")
        sys.exit(1)

    with open("last_created_games.json", "r") as f:
        game_history = json.load(f)

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
        print("Settlement calculation failed. Aborting announcement.")
        sys.exit(result.returncode)

    # 3. Read generated HTML report
    report_file = f"./output/settlement_{description}.html"
    if not os.path.exists(report_file):
        report_file = "./output/settlement.html"
        if not os.path.exists(report_file):
            print(f"Error: Settlement report file not found in ./output/")
            sys.exit(1)

    with open(report_file, "r", encoding="utf-8") as f:
        report_html = f.read()

    subject = f"Poker Settlement Payouts - {description}"
    
    # 4. Email/Discord the report
    send_email(subject, report_html)
    post_to_discord(subject, report_html)

if __name__ == "__main__":
    main()
