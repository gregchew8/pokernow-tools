from playwright.sync_api import sync_playwright
import os, time, subprocess

user_data_dir = os.path.abspath(os.path.join(os.getcwd(), "chrome-profile"))
chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

print("1. Writing fake cookie via Popen...")
cmd = [chrome_path, f"--user-data-dir={user_data_dir}", "--password-store=basic", "https://example.com"]
p = subprocess.Popen(cmd)
time.sleep(3)
subprocess.run(["osascript", "-e", 'tell application "Google Chrome" to close front window'])
time.sleep(2)
p.terminate()

print("2. Checking DB size...")
os.system(f"ls -la {user_data_dir}/Default/Cookies")

print("3. Launching Playwright...")
with sync_playwright() as pw:
    context = pw.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        executable_path=chrome_path,
        channel="chrome",
        args=["--password-store=basic"]
    )
    time.sleep(2)
    context.close()

print("4. Checking DB size...")
os.system(f"ls -la {user_data_dir}/Default/Cookies")
