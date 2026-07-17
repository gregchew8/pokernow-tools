from playwright.sync_api import sync_playwright
import os, time, subprocess, sqlite3, shutil

user_data_dir = os.path.abspath(os.path.join(os.getcwd(), "chrome-profile-test"))
copy_dir = user_data_dir + "-copy"
chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
os.system(f"rm -rf {user_data_dir} {copy_dir}")

def get_cookie_count(path):
    db_path = os.path.join(path, "Default", "Cookies")
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

print("1. Launching Popen to set cookie...")
cmd = [chrome_path, f"--user-data-dir={user_data_dir}", "--password-store=basic", "--no-first-run", "https://example.com"]
p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
# Hack to set a cookie via sqlite since example.com doesn't
db_path = os.path.join(user_data_dir, "Default", "Cookies")
conn = sqlite3.connect(db_path)
conn.execute("INSERT INTO cookies (host_key, name, value, path, expires_utc, is_secure, is_httponly, samesite, is_persistent, has_expires, is_ephemeral, source_scheme, source_port, last_update_utc) VALUES ('example.com', 'test', '123', '/', 0, 0, 0, 0, 1, 0, 0, 1, -1, 0)")
conn.commit()
conn.close()

subprocess.run(["osascript", "-e", 'tell application "Google Chrome" to close front window'])
time.sleep(2)
p.terminate()

print("Cookies in original:", get_cookie_count(user_data_dir))

print("2. Copying profile...")
shutil.copytree(user_data_dir, copy_dir)
print("Cookies in copy before Playwright:", get_cookie_count(copy_dir))

print("3. Launching Playwright on copy...")
with sync_playwright() as pw:
    context = pw.chromium.launch_persistent_context(
        user_data_dir=copy_dir,
        executable_path=chrome_path,
        channel="chrome",
        args=["--password-store=basic"]
    )
    page = context.new_page()
    page.goto("https://example.com")
    cookies = context.cookies()
    print("Playwright sees cookies:", len(cookies))
    time.sleep(2)
    context.close()

