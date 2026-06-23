import sys
import os

# Set custom Playwright browsers path to persist Chromium executable outside macOS Library cache sweeps
working_dir = os.path.dirname(os.path.abspath(__file__))
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(working_dir, "playwright-browsers")

from playwright.sync_api import sync_playwright


def main():
    print("Launching browser with automation flags disabled...")
    with sync_playwright() as p:
        # Launch Chromium using a persistent user data directory in our workspace
        # and disable the Blink features that flag it as an automated browser
        context = p.chromium.launch_persistent_context(
            user_data_dir="./chrome-profile",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = context.new_page()
        page.goto("https://www.pokernow.com")
        
        print("\n" + "="*60)
        print(" ACTION REQUIRED: Please log in to Poker Now (via Google or other method).")
        print(" Once you are successfully logged in, press ENTER here in the terminal to save.")
        print("="*60 + "\n")
        
        sys.stdin.readline()
        context.close()
    print("Login session saved to './chrome-profile' successfully!")


if __name__ == "__main__":
    main()
