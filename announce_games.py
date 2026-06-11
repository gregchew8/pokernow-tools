#!/usr/bin/env python3
import os
import sys
import json
import smtplib
import subprocess
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

def send_email(subject, html_content, text_content):
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    sender = os.environ.get("EMAIL_SENDER")
    password = os.environ.get("EMAIL_PASSWORD")
    receiver = os.environ.get("EMAIL_RECEIVER") # The Google Group email

    if not all([sender, password, receiver]):
        print("Skipping email announcement: EMAIL_SENDER, EMAIL_PASSWORD, or EMAIL_RECEIVER not set in environment.")
        return False

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = receiver

    part1 = MIMEText(text_content, 'plain')
    part2 = MIMEText(html_content, 'html')
    msg.attach(part1)
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
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

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
    import datetime
    
    args = sys.argv[1:]
    
    # If no arguments are passed, load dynamically from schedule.json based on the day of the week
    if not args:
        # Get local time in PST/PDT by offsetting UTC by 7 hours (reliable for local day of week at 5:00 PM)
        local_now = datetime.datetime.utcnow() - datetime.timedelta(hours=7)
        day_name = local_now.strftime("%A").lower()
        print(f"No arguments provided. Detecting game night day of week: {day_name.capitalize()}")
        
        schedule_file = "schedule.json"
        if os.path.exists(schedule_file):
            try:
                with open(schedule_file, "r") as f:
                    schedule_data = json.load(f)
                day_config = schedule_data.get(day_name)
                
                if day_config and isinstance(day_config, list):
                    config_str = json.dumps(day_config)
                    args = ["--config", config_str]
                    print(f"Loaded schedule for {day_name.capitalize()}: {day_config}")
                else:
                    print(f"Warning: No schedule config list defined in '{schedule_file}' for '{day_name}'. Defaulting to 'nlh 2' with 0.25/0.50 blinds.")
                    args = ["nlh", "2", "--sb", "0.25", "--bb", "0.50"]
            except Exception as e:
                print(f"Error reading {schedule_file}: {e}. Defaulting to 'nlh 2'.")
                args = ["nlh", "2", "--sb", "0.25", "--bb", "0.50"]
        else:
            print(f"Warning: {schedule_file} not found. Defaulting to 'nlh 2'.")
            args = ["nlh", "2", "--sb", "0.25", "--bb", "0.50"]

    # Pass all args (like game types/counts) to setup_poker_auth.py, adding --headless
    setup_cmd = [sys.executable, "setup_poker_auth.py", "--headless"] + args
    
    print(f"Running table creation: {' '.join(setup_cmd)}")
    result = subprocess.run(setup_cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if result.returncode != 0:
        print("Table creation failed. Aborting announcement.")
        sys.exit(result.returncode)

    # Read the created games JSON
    if not os.path.exists("last_created_games.json"):
        print("Error: last_created_games.json not found.")
        sys.exit(1)

    with open("last_created_games.json", "r") as f:
        game_data = f.read()
        print("Created games details:")
        print(game_data)
        game_history = json.loads(game_data)

    date_str = game_history.get("date", "")
    tables = game_history.get("tables", [])
    
    subject = f"Poker Night Tables for {date_str}"
    
    # Construct Email/Discord content
    text_lines = [subject, "Here are the table links for tonight's games:", ""]
    html_lines = [f"<h2>{subject}</h2>", "<p>Here are the table links for tonight's games:</p><ul>"]
    
    for t in tables:
        game_type = t.get("game_type", "").upper()
        table_num = t.get("table_num", 1)
        game_id = t.get("game_id", "")
        url = f"https://www.pokernow.club/games/{game_id}"
        
        text_lines.append(f"- {game_type} Table {table_num}: {url}")
        html_lines.append(f"<li><strong>{game_type} Table {table_num}:</strong> <a href=\"{url}\">{url}</a></li>")
        
    text_lines.append("")
    text_lines.append("Good luck at the tables!")
    
    html_lines.append("</ul><p>Good luck at the tables!</p>")
    
    text_content = "\n".join(text_lines)
    html_content = "\n".join(html_lines)
    
    # Send email
    send_email(subject, html_content, text_content)
    
    # Post to Discord
    post_to_discord(subject, text_content)

if __name__ == "__main__":
    main()
