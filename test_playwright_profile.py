from playwright.sync_api import sync_playwright
import os

user_data_dir = os.path.abspath(os.path.join(os.getcwd(), "chrome-profile"))
chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        executable_path=chrome_path,
        channel="chrome",
        args=["--password-store=basic"]
    )
    page = context.new_page()
    page.goto("https://www.pokernow.com")
    
    # Check if localStorage has npt token
    token = page.evaluate("localStorage.getItem('npt')")
    print(f"Token in Playwright: {token}")
    
    # Check cookies
    cookies = context.cookies()
    google_cookies = [c['name'] for c in cookies if 'google' in c['domain']]
    print(f"Google Cookies in Playwright: {len(google_cookies)}")
    
    context.close()
