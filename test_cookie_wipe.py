from playwright.sync_api import sync_playwright
import os, time, subprocess, sqlite3

user_data_dir = os.path.abspath(os.path.join(os.getcwd(), "chrome-profile-test"))
chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
os.system(f"rm -rf {user_data_dir}")

def get_cookie_count():
    db_path = os.path.join(user_data_dir, "Default", "Cookies")
    if not os.path.exists(db_path): return -1
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT count(*) FROM cookies")
        count = c.fetchone()[0]
        conn.close()
        return count
    except:
        return -2

print("1. Launching Playwright to set cookie...")
with sync_playwright() as pw:
    context = pw.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        executable_path=chrome_path,
        channel="chrome",
        args=["--password-store=basic"]
    )
    page = context.new_page()
    page.goto("https://example.com")
    context.add_cookies([{"name": "test", "value": "123", "domain": "example.com", "path": "/"}])
    time.sleep(2)
    context.close()

print("Cookies after Playwright 1:", get_cookie_count())

print("2. Launching Popen...")
cmd = [chrome_path, f"--user-data-dir={user_data_dir}", "--password-store=basic", "--no-first-run", "https://example.com"]
p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
subprocess.run(["osascript", "-e", 'tell application "Google Chrome" to close front window'])
time.sleep(2)
p.terminate()

print("Cookies after Popen:", get_cookie_count())

print("3. Launching Playwright 2...")
with sync_playwright() as pw:
    context = pw.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        executable_path=chrome_path,
        channel="chrome",
        args=["--password-store=basic"]
    )
    time.sleep(2)
    context.close()

print("Cookies after Playwright 2:", get_cookie_count())
