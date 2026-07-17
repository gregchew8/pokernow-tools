import subprocess
import time

url_check = """
tell application "Google Chrome"
    return URL of active tab of front window
end tell
"""
print("Current URL:", subprocess.run(["osascript", "-e", url_check], capture_output=True, text=True).stdout.strip())
