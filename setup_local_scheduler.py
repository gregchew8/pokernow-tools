#!/usr/bin/env python3
import os
import sys
import subprocess

GAME_NIGHTS_LABEL = "com.pokernow.game_nights"
NEXT_MORNING_LABEL = "com.pokernow.next_morning"
WEB_UI_LABEL = "com.pokernow.web_ui"

WEB_UI_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{script_path}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{working_dir}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{working_dir}/output/web_ui_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{working_dir}/output/web_ui_stderr.log</string>
</dict>
</plist>
"""

GAME_NIGHT_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{script_path}</string>
        <string>--scheduled</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{working_dir}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
        <key>PLAYWRIGHT_BROWSERS_PATH</key>
        <string>{working_dir}/playwright-browsers</string>
    </dict>
    <key>StartCalendarInterval</key>
    <array>
        <!-- Monday 5:00 PM (Weekday 1) -->
        <dict>
            <key>Hour</key>
            <integer>17</integer>
            <key>Minute</key>
            <integer>0</integer>
            <key>Weekday</key>
            <integer>1</integer>
        </dict>
        <!-- Wednesday 5:00 PM (Weekday 3) -->
        <dict>
            <key>Hour</key>
            <integer>17</integer>
            <key>Minute</key>
            <integer>0</integer>
            <key>Weekday</key>
            <integer>3</integer>
        </dict>
        <!-- Friday 5:00 PM (Weekday 5) -->
        <dict>
            <key>Hour</key>
            <integer>17</integer>
            <key>Minute</key>
            <integer>0</integer>
            <key>Weekday</key>
            <integer>5</integer>
        </dict>
        <!-- Saturday 5:00 PM (Weekday 6) -->
        <dict>
            <key>Hour</key>
            <integer>17</integer>
            <key>Minute</key>
            <integer>0</integer>
            <key>Weekday</key>
            <integer>6</integer>
        </dict>
    </array>
    <key>StandardOutPath</key>
    <string>{working_dir}/output/game_nights_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{working_dir}/output/game_nights_stderr.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
"""

NEXT_MORNING_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{script_path}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{working_dir}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
        <key>PLAYWRIGHT_BROWSERS_PATH</key>
        <string>{working_dir}/playwright-browsers</string>
    </dict>
    <key>StartCalendarInterval</key>
    <array>
        <!-- Tuesday 8:00 AM (Weekday 2) -->
        <dict>
            <key>Hour</key>
            <integer>8</integer>
            <key>Minute</key>
            <integer>0</integer>
            <key>Weekday</key>
            <integer>2</integer>
        </dict>
        <!-- Thursday 8:00 AM (Weekday 4) -->
        <dict>
            <key>Hour</key>
            <integer>8</integer>
            <key>Minute</key>
            <integer>0</integer>
            <key>Weekday</key>
            <integer>4</integer>
        </dict>
        <!-- Saturday 8:00 AM (Weekday 6) -->
        <dict>
            <key>Hour</key>
            <integer>8</integer>
            <key>Minute</key>
            <integer>0</integer>
            <key>Weekday</key>
            <integer>6</integer>
        </dict>
        <!-- Sunday 8:00 AM (Weekday 0) -->
        <dict>
            <key>Hour</key>
            <integer>8</integer>
            <key>Minute</key>
            <integer>0</integer>
            <key>Weekday</key>
            <integer>0</integer>
        </dict>
    </array>
    <key>StandardOutPath</key>
    <string>{working_dir}/output/next_morning_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{working_dir}/output/next_morning_stderr.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
"""

def main():
    working_dir = os.getcwd()
    python_path = sys.executable
    
    launch_agents_dir = os.path.expanduser("~/Library/LaunchAgents")
    os.makedirs(launch_agents_dir, exist_ok=True)
    os.makedirs(os.path.join(working_dir, "output"), exist_ok=True)

    game_nights_path = os.path.join(launch_agents_dir, f"{GAME_NIGHTS_LABEL}.plist")
    next_morning_path = os.path.join(launch_agents_dir, f"{NEXT_MORNING_LABEL}.plist")
    web_ui_path = os.path.join(launch_agents_dir, f"{WEB_UI_LABEL}.plist")

    # Format the plists
    game_nights_content = GAME_NIGHT_PLIST.format(
        label=GAME_NIGHTS_LABEL,
        python_path=python_path,
        script_path=os.path.join(working_dir, "announce_games.py"),
        working_dir=working_dir
    )

    next_morning_content = NEXT_MORNING_PLIST.format(
        label=NEXT_MORNING_LABEL,
        python_path=python_path,
        script_path=os.path.join(working_dir, "auto_settle.py"),
        working_dir=working_dir
    )

    web_ui_content = WEB_UI_PLIST.format(
        label=WEB_UI_LABEL,
        python_path=python_path,
        script_path=os.path.join(working_dir, "local_agent.py"),
        working_dir=working_dir
    )

    import plistlib
    import json
    
    # Read schedule.json to build intervals
    schedule_path = os.path.join(working_dir, "schedule.json")
    schedule_data = {}
    if os.path.exists(schedule_path):
        with open(schedule_path, "r") as f:
            schedule_data = json.load(f)
            
    days_map = {
        "monday": 1, "tuesday": 2, "wednesday": 3, "thursday": 4,
        "friday": 5, "saturday": 6, "sunday": 0
    }
    
    gn_intervals = []
    nm_intervals = []
    
    for day, config in schedule_data.items():
        if day not in days_map or not isinstance(config, dict): continue
        weekday = days_map[day]
        next_weekday = (weekday + 1) % 7
        
        setup_time = config.get("setup_time")
        if setup_time:
            h, m = map(int, setup_time.split(':'))
            gn_intervals.append({"Hour": h, "Minute": m, "Weekday": weekday})
            
        settlement_time = config.get("settlement_time")
        if settlement_time:
            h, m = map(int, settlement_time.split(':'))
            nm_intervals.append({"Hour": h, "Minute": m, "Weekday": next_weekday})

    def write_plist(path, template_content, intervals):
        pl_new = plistlib.loads(template_content.encode('utf-8'))
        pl_new["StartCalendarInterval"] = intervals
        with open(path, 'wb') as f:
            plistlib.dump(pl_new, f)
        print(f"Created/Updated: {path}")

    # Remove the old preserve_and_write fallback, we now force intervals from schedule.json
    write_plist(game_nights_path, game_nights_content, gn_intervals)
    write_plist(next_morning_path, next_morning_content, nm_intervals)
    
    # For web_ui, there is no StartCalendarInterval, just dump it
    web_pl = plistlib.loads(web_ui_content.encode('utf-8'))
    with open(web_ui_path, 'wb') as f:
        plistlib.dump(web_pl, f)
    print(f"Created/Updated: {web_ui_path}")
    
    agents_list = [
        (GAME_NIGHTS_LABEL, game_nights_path),
        (NEXT_MORNING_LABEL, next_morning_path)
    ]
    if "--skip-web-ui" not in sys.argv:
        agents_list.append((WEB_UI_LABEL, web_ui_path))

    for label, plist_path in agents_list:
        subprocess.run(["launchctl", "unload", plist_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Load the launch agent
        res = subprocess.run(["launchctl", "load", plist_path], capture_output=True, text=True)
        if res.returncode == 0:
            print(f"Successfully loaded and scheduled LaunchAgent: {label}")
        else:
            print(f"Error loading {label}: {res.stderr.strip()}")

    # Remind the user to copy .env
    env_file = os.path.join(working_dir, ".env")
    if not os.path.exists(env_file):
        print("\n" + "="*70)
        print(" IMPORTANT NEXT STEP:")
        print("="*70)
        print(" Please create a '.env' file in this folder using '.env.template' as a model.")
        print(" Fill in your Google Sheet URL, SMTP details, and/or Discord Webhook.")
        print("="*70 + "\n")
    else:
        print("\nSetup complete! Local schedulers have been loaded and scheduled.")

if __name__ == "__main__":
    main()
