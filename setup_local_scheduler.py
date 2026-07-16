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
        script_path=os.path.join(working_dir, "web_ui.py"),
        working_dir=working_dir
    )

    import plistlib
    def preserve_and_write(path, template_content):
        existing_intervals = None
        if os.path.exists(path):
            try:
                with open(path, 'rb') as f:
                    pl = plistlib.load(f)
                    existing_intervals = pl.get("StartCalendarInterval")
            except Exception:
                pass
        
        try:
            pl_new = plistlib.loads(template_content.encode('utf-8'))
            if existing_intervals:
                pl_new["StartCalendarInterval"] = existing_intervals
            with open(path, 'wb') as f:
                plistlib.dump(pl_new, f)
            print(f"Created/Updated: {path}")
        except Exception as e:
            # Fallback if there's an issue with plistlib
            with open(path, "w") as f:
                f.write(template_content)
            print(f"Created: {path}")

    preserve_and_write(game_nights_path, game_nights_content)
    preserve_and_write(next_morning_path, next_morning_content)
    preserve_and_write(web_ui_path, web_ui_content)
    agents_list = [
        (GAME_NIGHTS_LABEL, game_nights_path),
        (NEXT_MORNING_LABEL, next_morning_path),
        (WEB_UI_LABEL, web_ui_path)
    ]
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
