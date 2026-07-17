from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto("https://www.pokernow.com/start-game")
    
    # Fill Nickname and click Start Game
    page.locator("input[type='text']").fill("GuestTest")
    buttons = page.locator("button").all()
    for btn in buttons:
        text = btn.inner_text().lower()
        if "start" in text or "create" in text:
            btn.click()
            break
            
    page.wait_for_url("**/games/**")
    time.sleep(2)
    
    # Click Options -> Game Configurations
    page.locator("button:has-text('Options')").click()
    time.sleep(1)
    page.locator("button:has-text('Game Configurations')").click()
    page.wait_for_selector(".modal")
    time.sleep(1)
    
    # Dump the modal HTML
    html = page.locator(".modal").inner_html()
    with open("modal_html.txt", "w") as f:
        f.write(html)
        
    browser.close()
