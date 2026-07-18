import sys
import os
import subprocess
import time
import urllib.request

# Set custom Playwright browsers path to persist Chromium executable outside macOS Library cache sweeps
working_dir = os.path.dirname(os.path.abspath(__file__))
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(working_dir, "playwright-browsers")

from playwright.sync_api import sync_playwright


def main():
    user_data_dir = os.path.abspath("./chrome-profile")
    port = 9228
    
    # Try to clean up any leftover Chrome profiles
    subprocess.run(["pkill", "-f", "chrome-profile"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    
    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    cmd = [
        chrome_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--password-store=basic",
        "https://www.pokernow.com"
    ]
    
    print("Launching standard Google Chrome via subprocess...")
    chrome_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Wait for the debugging port to open (up to 5 seconds)
    connected = False
    for _ in range(50):
        try:
            with urllib.request.urlopen(f"http://localhost:{port}/json/version", timeout=1) as response:
                if response.status == 200:
                    connected = True
                    break
        except Exception:
            pass
        time.sleep(0.1)
        
    if not connected:
        print("Error: Failed to launch Google Chrome with remote debugging.")
        return
        
    print("Connecting Playwright to the launched Chrome browser...")
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://localhost:{port}")
        context = browser.contexts[0]
        context.add_init_script("delete navigator.__proto__.webdriver;")
        
        page = context.pages[0] if context.pages else context.new_page()
        if "pokernow.com" not in page.url:
            page.goto("https://www.pokernow.com")
        
        print("\n" + "="*60)
        print(" ACTION REQUIRED: Please log in to Poker Now (via Google or other method).")
        print(" Once you are successfully logged in, press ENTER here in the terminal to save.")
        print("="*60 + "\n")
        
        sys.stdin.readline()
        print("Syncing login session to disk... please wait a few seconds.")
        time.sleep(3.0)
        try:
            context.close()
            browser.close()
        except Exception:
            pass # Browser was already closed manually by user
            
    # Gracefully close the window so Chrome flushes localStorage to disk
    subprocess.run(["osascript", "-e", 'tell application "Google Chrome" to close front window'], capture_output=True)
    time.sleep(3.0)
    
    chrome_process.terminate()
    try:
        chrome_process.wait(timeout=5)
    except Exception:
        chrome_process.kill()
    print("Login session saved to './chrome-profile' successfully!")


if __name__ == "__main__":
    main()
