#!/usr/bin/env python3
import os
import sys
import json
import smtplib
import subprocess
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

def send_email(subject, html_content, text_content, email_type="announcement"):
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
        if email_type == "diagnostic":
            print(f"Diagnostic alert email sent successfully to {receiver}")
        else:
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
    working_dir = os.path.dirname(os.path.abspath(__file__))
    drive_path = os.environ.get("GOOGLE_DRIVE_PATH")
    if not drive_path:
        print("Skipping Google Drive backup: GOOGLE_DRIVE_PATH not set in environment.")
        return
    if not os.path.exists(drive_path):
        print(f"Skipping Google Drive backup: path {drive_path} does not exist.")
        return
    
    print("\nBacking up files to Google Drive...")
    src = working_dir + "/"
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
    
    is_test = "--test" in args
    is_draft = "--draft" in args
    args = [a for a in args if a not in ("--test", "--draft")]
    

    # Handle test mode: simulate dummy game creation
    if is_test:
        print("\n=== TEST MODE ===")
        dummy_urls = []
        # Simple dummy tables for testing
        dummy_tables = [{"type": "nlh", "sb": "0.25", "bb": "0.50"}]
        for idx, tbl in enumerate(dummy_tables, start=1):
            game_type = tbl["type"]
            sb = tbl["sb"]
            bb = tbl["bb"]
            dummy_url = f"https://www.pokernow.com/games/test_{idx}"
            dummy_urls.append((game_type, dummy_url))
        today = datetime.datetime.now()
        game_history = {
            "date": today.strftime("%Y-%m-%d"),
            "description": today.strftime("%m%d%y"),
            "game_ids": [url.split("/games/")[-1] for _, url in dummy_urls],
            "tables": [],
            "is_adhoc": False
        }
        for tbl, url in dummy_urls:
            game_history["tables"].append({
                "game_type": tbl,
                "table_num": 1,
                "sb": "0.25",
                "bb": "0.50",
                "game_id": url.split("/games/")[-1]
            })
        with open("last_created_games.json", "w") as f:
            json.dump(game_history, f, indent=4)
        print("Test mode: dummy game data written to 'last_created_games.json'.")
        sys.exit(0)

    # If no arguments are provided, determine the current day and create tables based on schedule.json
    if not args:
        # Determine local current time in PST/PDT (UTC-7)
        local_now = datetime.datetime.utcnow() - datetime.timedelta(hours=7)
        day_name = local_now.strftime("%A").lower()
        print(f"No arguments provided. Detecting game night day of week: {day_name.capitalize()}")
        
        schedule_file = "schedule.json"
        if os.path.exists(schedule_file):
            try:
                with open(schedule_file, "r") as f:
                    schedule_data = json.load(f)
                day_config = schedule_data.get(day_name)
                if isinstance(day_config, dict):
                    tables = day_config.get("tables", [])
                    if tables:
                        print(f"Loaded schedule for {day_name.capitalize()}: {tables}")
                        # Run setup for each table individually
                        for tbl in tables:
                            game_type = tbl.get("type", "nlh")
                            sb = tbl.get("sb", "0.25")
                            bb = tbl.get("bb", "0.50")
                            table_args = [game_type, "1", "--sb", sb, "--bb", bb]
                            print(f"Running table creation: {' '.join([sys.executable, 'setup_poker_auth.py'] + table_args)}")
                            result = subprocess.run([sys.executable, "setup_poker_auth.py"] + table_args,
                                                    capture_output=True, text=True)
                            print(result.stdout)
                            if result.stderr:
                                print(result.stderr, file=sys.stderr)
                            if result.returncode != 0:
                                raise RuntimeError(f"Table creation failed for {game_type} with sb={sb}, bb={bb}. Exit code {result.returncode}\n{result.stderr}")
                        # After creating tables, clear args to skip final call
                        args = []
                    else:
                        print(f"Warning: No tables defined for {day_name} in {schedule_file}. Using default configuration.")
                        args = ["nlh", "2", "--sb", "0.25", "--bb", "0.50"]
                else:
                    print(f"Warning: Unexpected format for {day_name} in {schedule_file}. Using default configuration.")
                    args = ["nlh", "2", "--sb", "0.25", "--bb", "0.50"]
            except Exception as e:
                print(f"Error reading {schedule_file}: {e}. Using default configuration.")
                args = ["nlh", "2", "--sb", "0.25", "--bb", "0.50"]
        else:
            print(f"Warning: {schedule_file} not found. Using default configuration.")
            args = ["nlh", "2", "--sb", "0.25", "--bb", "0.50"]

    # Pass all args (like game types/counts) to setup_poker_auth.py (headed by default to bypass Cloudflare bot check)
    if args:
        setup_cmd = [sys.executable, "setup_poker_auth.py"] + args
        import time
        start_time = time.time()
        print(f"Running table creation: {' '.join(setup_cmd)}")
        result = subprocess.run(setup_cmd, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        if result.returncode != 0:
            error_details = result.stderr.strip() if result.stderr else result.stdout.strip()
            raise RuntimeError(f"Table creation failed. setup_poker_auth.py exited with code {result.returncode}.\n\nSubprocess Output:\n{error_details}")
    else:
        # No additional args; tables already created in the loop above.
        import time
        start_time = time.time()
        print("Skipping final setup_poker_auth.py call because tables were already created.")

    # Read the created games JSON
    import errno
    game_data = None
    for attempt in range(10):
        try:
            if os.path.exists("last_created_games.json"):
                mtime = os.path.getmtime("last_created_games.json")
                if mtime < start_time:
                    raise RuntimeError("setup_poker_auth.py exited cleanly but did not create new tables (last_created_games.json is stale).")
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
    
    if is_test:
        print("\n=== TEST MODE ===")
        print("Calculations & table creation complete. Notifications, Discord, Calendar sync, and Drive backup bypassed.")
        print(text_content)
    elif is_draft:
        draft_data = {
            "type": "announcer",
            "subject": subject,
            "html_content": html_content,
            "text_content": text_content
        }
        with open("pending_email.json", "w") as f:
            json.dump(draft_data, f, indent=4)
        print("\n=== Email Draft Saved: Awaiting Approval ===")
        print("Note: This was created in DRAFT mode. The game announcement email was NOT sent to the players.")
        print("Instructions to send:")
        print(" 1. Open the Poker Now Control Panel (via Tailscale on port 8080 or poker.gchew.com).")
        print(" 2. Scroll to the 'Pending Emails Awaiting Approval' card.")
        print(" 3. Review the subject and HTML body draft.")
        print(" 4. Click 'Approve & Send' to dispatch the email to your players, or 'Delete' to discard it.")
    else:
        # Send email
        send_email(subject, html_content, text_content)
        # Post to Discord
        post_to_discord(subject, text_content)

    if not is_test:
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
            # 1. Send the basic error email to the admin group
            subject = f"ALERT: Poker Game Announcer Failed ({datetime.datetime.now().strftime('%Y-%m-%d')})"
            basic_html = f"<h3>Poker Game Announcer Failed</h3><p>The scheduled background task encountered an error:</p><pre style='color: red; padding: 10px; background: #f9f9f9; border: 1px solid #ccc;'>{error_msg}</pre>"
            basic_text = f"Poker Game Announcer Failed\n\nError details:\n{error_msg}"
            
            original_receiver = os.environ.get("EMAIL_RECEIVER")
            os.environ["EMAIL_RECEIVER"] = admin_email
            send_email(subject, basic_html, basic_text, email_type="diagnostic")
            
            # 2. Send the verbose instructions specifically to Greg
            greg_subject = f"ACTION REQUIRED: Poker Game Announcer Failed ({datetime.datetime.now().strftime('%Y-%m-%d')})"
            greg_html = f"""
            <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; color: #333;">
                <h2 style="color: #ef4444;">🚨 Poker Game Announcer Failed</h2>
                <p>The scheduled background task to setup Poker Now tables encountered a critical error and could not complete.</p>
                
                <div style="background: #f8fafc; border-left: 4px solid #3b82f6; padding: 15px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #1e3a8a;">Next Steps for Greg:</h3>
                    <ol style="margin-bottom: 0;">
                        <li>Review the detailed technical stack trace below to identify the issue.</li>
                        <li>Open the <strong><a href="http://localhost:8080">Poker Now Control Panel</a></strong> (accessible via Tailscale IP on port 8080).</li>
                        <li>Look at the <strong>System Logs</strong> section. The <em>Diagnostic Advisor</em> will automatically provide triaged recovery steps.</li>
                        <li>If the issue was a temporary network glitch or missing dependency, simply click <strong>Start Table Setup</strong> in the Game Announcer card on the Control Panel to manually retry the creation!</li>
                    </ol>
                </div>
                
                <p><strong>Technical Error Details:</strong></p>
                <pre style="color: #b91c1c; padding: 15px; background: #fef2f2; border: 1px solid #f87171; overflow-x: auto; font-size: 12px; border-radius: 4px;">{error_msg}</pre>
            </div>
            """
            greg_text = f"Poker Game Announcer Failed\n\nNext Steps for Greg:\n1. Open the Poker Now Control Panel (via Tailscale on port 8080).\n2. Review the System Logs section for Diagnostic Advisor recovery steps.\n3. Click 'Start Table Setup' to try again once fixed.\n\nError details:\n{error_msg}"
            
            os.environ["EMAIL_RECEIVER"] = "gregchew@gmail.com"
            send_email(greg_subject, greg_html, greg_text, email_type="diagnostic")
            
            # Restore original receiver
            if original_receiver:
                os.environ["EMAIL_RECEIVER"] = original_receiver
            else:
                del os.environ["EMAIL_RECEIVER"]
        sys.exit(1)
