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
    email_from = os.environ.get("EMAIL_FROM", f"LCR Admins <{sender}>")
    reply_to = os.environ.get("EMAIL_REPLY_TO", "noreply@lcr-poker.com")

    if not all([sender, password, receiver]):
        print("Skipping email announcement: EMAIL_SENDER, EMAIL_PASSWORD, or EMAIL_RECEIVER not set in environment.")
        return False

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = email_from
    msg['To'] = receiver
    msg['Reply-To'] = reply_to

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

    # Pass all args (like game types/counts) to setup_poker_auth.py (headed by default to bypass Cloudflare bot check)
    setup_cmd = [sys.executable, "setup_poker_auth.py"] + args
    
    print(f"Running table creation: {' '.join(setup_cmd)}")
    result = subprocess.run(setup_cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if result.returncode != 0:
        error_details = result.stderr.strip() if result.stderr else result.stdout.strip()
        raise RuntimeError(f"Table creation failed. setup_poker_auth.py exited with code {result.returncode}.\n\nSubprocess Output:\n{error_details}")

    # Read the created games JSON
    import time
    import errno
    game_data = None
    for attempt in range(10):
        try:
            if os.path.exists("last_created_games.json"):
                with open("last_created_games.json", "r") as f:
                    game_data = f.read()
                break
        except OSError as e:
            if e.errno in (errno.EDEADLK, errno.EAGAIN) and attempt < 9:
                print(f"Google Drive sync lock detected, retrying read from last_created_games.json ({attempt + 1}/10)...")
                time.sleep(1.0)
            else:
                raise

    if not game_data:
        raise FileNotFoundError("Error: last_created_games.json not found or could not be read.")

    print("Created games details:")
    print(game_data)
    game_history = json.loads(game_data)

    tables = game_history.get("tables", [])
    today = datetime.datetime.now()
    day = today.day
    month_abbr = today.strftime("%b")
    suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    subject = f"Cash Game Tonight ({month_abbr} {day}{suffix}, 7PM)"
    
    # Construct Email/Discord content
    text_lines = [subject, "Here are the table links for tonight's games:", ""]
    html_lines = [f"<h2>{subject}</h2>", "<p>Here are the table links for tonight's games:</p><ul>"]
    
    for t in tables:
        game_type = t.get("game_type", "").upper()
        table_num = t.get("table_num", 1)
        game_id = t.get("game_id", "")
        sb = t.get("sb")
        bb = t.get("bb")
        stakes_suffix = f" {sb}/{bb}" if sb and bb else ""
        url = f"https://www.pokernow.club/games/{game_id}"
        
        text_lines.append(f"- {game_type}{stakes_suffix} Table {table_num}: {url}")
        html_lines.append(f"<li><strong><a href=\"{url}\">{game_type}{stakes_suffix} Table {table_num}</a></strong></li>")
        
    note_text = "The first person sitting at the table will be the first admin of the table for the night. Please shuffle the seats and start the tables when the players are ready to start"
    feedback_text = "For any issues, questions, suggestions, or things we can improve on, please send feedback to lcr-poker-admins@gmail.com."
    
    text_lines.append("")
    text_lines.append(note_text)
    text_lines.append("")
    text_lines.append("Good luck at the tables!")
    text_lines.append("")
    text_lines.append(feedback_text)
    
    html_lines.append(f"</ul><p style=\"color: #555; font-style: italic;\">{note_text}</p><p>Good luck at the tables!</p><p style=\"font-size: 0.9rem; color: #666; border-top: 1px solid #ddd; padding-top: 10px; margin-top: 20px;\">For any issues, questions, suggestions, or things we can improve on, please send feedback to <a href=\"mailto:lcr-poker-admins@gmail.com\">lcr-poker-admins@gmail.com</a>.</p>")
    
    text_content = "\n".join(text_lines)
    html_content = "\n".join(html_lines)
    
    if "--draft" in sys.argv:
        draft_data = {
            "type": "announcer",
            "subject": subject,
            "html_content": html_content,
            "text_content": text_content
        }
        with open("pending_email.json", "w") as f:
            json.dump(draft_data, f, indent=4)
        print("\n=== Email Draft Saved: Awaiting Approval ===")
    else:
        # Send email
        send_email(subject, html_content, text_content)
        # Post to Discord
        post_to_discord(subject, text_content)

    # Sync to Google Calendar
    print("\nStep 4: Syncing to Google Calendar...")
    subprocess.run([sys.executable, "update_calendar.py"])
    
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
            subject = f"ALERT: Poker Game Announcer Failed ({datetime.datetime.now().strftime('%Y-%m-%d')})"
            html_content = f"<h3>Poker Game Announcer Failed</h3><p>The scheduled background task encountered an error:</p><pre style='color: red; padding: 10px; background: #f9f9f9; border: 1px solid #ccc;'>{error_msg}</pre>"
            text_content = f"Poker Game Announcer Failed\n\nError details:\n{error_msg}"
            
            original_receiver = os.environ.get("EMAIL_RECEIVER")
            os.environ["EMAIL_RECEIVER"] = admin_email
            send_email(subject, html_content, text_content)
            if original_receiver:
                os.environ["EMAIL_RECEIVER"] = original_receiver
        sys.exit(1)
