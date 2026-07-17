import subprocess, time

applescript = """
tell application "Google Chrome"
    return URL of active tab of front window
end tell
"""
res = subprocess.run(["osascript", "-e", applescript], capture_output=True, text=True)
print(res.stdout)
