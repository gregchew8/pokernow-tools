import subprocess
import os
import time

user_data_dir = os.path.abspath("./chrome-profile")
chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Force a truly independent instance
cmd = [
    chrome_path,
    f"--user-data-dir={user_data_dir}",
    "--no-first-run",
    "--no-default-browser-check",
    "https://www.pokernow.com"
]

print("Launching Chrome. Let's see if you are logged in...")
proc = subprocess.Popen(cmd)
proc.wait()
