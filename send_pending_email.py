#!/usr/bin/env python3
import os
import sys
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

WORKING_DIR = "/Users/gregchew/pokernow"

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

def post_to_discord(subject, text_content):
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        return False

    import requests
    payload = {
        "content": f"**{subject}**\n\n{text_content}"
    }
    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        print("Discord announcement posted successfully.")
        return True
    except Exception as e:
        print(f"Error posting to Discord: {e}")
        return False

def main():
    load_env()
    draft_file = os.path.join(WORKING_DIR, "pending_email.json")
    if not os.path.exists(draft_file):
        print("Error: No pending email draft found.")
        sys.exit(1)

    try:
        with open(draft_file, "r") as f:
            draft = json.load(f)
    except Exception as e:
        print(f"Error reading draft: {e}")
        sys.exit(1)

    subject = draft.get("subject")
    html_content = draft.get("html_content")
    text_content = draft.get("text_content", "")
    
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    sender = os.environ.get("EMAIL_SENDER")
    password = os.environ.get("EMAIL_PASSWORD")
    receiver = os.environ.get("EMAIL_RECEIVER")

    if not all([sender, password, receiver]):
        print("Error: SMTP credentials or receiver not configured in .env.")
        sys.exit(1)

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"LCR Admins <{sender}>"
    msg['To'] = receiver

    if text_content:
        part1 = MIMEText(text_content, 'plain')
        msg.attach(part1)
    
    part2 = MIMEText(html_content, 'html')
    msg.attach(part2)

    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
            
        server.login(sender, password)
        server.sendmail(sender, receiver, msg.as_string())
        server.quit()
        print(f"Email announcement sent successfully to {receiver}")
        
        # Post to Discord
        post_to_discord(subject, text_content)
        
        # Remove pending draft
        os.remove(draft_file)
        print("Draft email file removed successfully.")
        
        # Run Google Drive sync to replicate deletion
        drive_path = "/Users/gregchew/Library/CloudStorage/GoogleDrive-gregchew@gmail.com/My Drive/pokernow"
        if os.path.exists(drive_path):
            import subprocess
            subprocess.run(["rsync", "-av", "--delete", "--exclude=chrome-profile", "--exclude=.git", WORKING_DIR + "/", drive_path + "/"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
    except Exception as e:
        print(f"Error sending email: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
