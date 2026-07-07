import os
import sys
import time
import json
import argparse
import subprocess
import datetime

def run_applescript(script):
    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return res.stdout.strip()

def inject_js(js_code):
    # Escape quotes and backslashes for AppleScript string literal
    escaped_js = js_code.replace('\\', '\\\\').replace('"', '\\"')
    script = f"""
    tell application "Google Chrome"
        execute front window's active tab javascript "{escaped_js}"
    end tell
    """
    return run_applescript(script)

def run(tables_to_create):
    user_data_dir = os.path.abspath(os.path.join(os.getcwd(), "chrome-profile"))
    if not os.path.exists(user_data_dir):
        print("Please run login.py first to authenticate with Google.")
        return

    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    urls = []
    total_tables = len(tables_to_create)
    
    # 1. Open the Turnstile-bypassing Chrome window
    print("Launching clean Google Chrome instance to evade Turnstile...")
    cmd = [
        chrome_path,
        f"--user-data-dir={user_data_dir}",
        "--password-store=basic",
        "--no-first-run",
        "--no-default-browser-check",
        "https://www.pokernow.com/start-game"
    ]
    
    # Launch main process natively - NO Playwright Debugging Ports!
    chrome_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(5.0)
    
    for idx, table_info in enumerate(tables_to_create):
        if len(table_info) == 4:
            game_type, table_num, sb, bb = table_info
        else:
            game_type, table_num = table_info
            sb, bb = "0.25", "0.50"
            
        print(f"\n============================================================")
        print(f" TABLE {idx+1} of {total_tables}: {game_type.upper()} ({sb}/{bb})")
        print(f"============================================================")
        
        if idx > 0:
            print("Opening new tab for next table...")
            inject_js("window.open('https://www.pokernow.com/start-game', '_blank');")
            time.sleep(3)
        
        print("\n" + "="*60)
        print(f" ACTION REQUIRED FOR TABLE {idx+1}:")
        print(" 1. In the Chrome window, click the Turnstile checkbox ('Verify you are human').")
        print(" The script will automatically detect the game and configure it instantly!")
        print("="*60 + "\n")
        
        detected_url = None
        for _ in range(120): # Wait up to 120 seconds for manual Turnstile bypass
            url = run_applescript('tell application "Google Chrome" to return URL of active tab of front window')
            if url and "pokernow.com/games/" in url:
                detected_url = url
                break
                
            if "start-game" in url:
                # Inject JS to fill Nickname (if empty) and click Create
                js = """
                var input = document.querySelector('input[placeholder*="Nickname"]') || document.querySelector('input[type="text"]') || document.querySelector('input');
                if (input) {
                    if (input.value !== 'Dealer') {
                        input.focus();
                        input.value = '';
                        document.execCommand('insertText', false, 'Dealer');
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    var buttons = document.querySelectorAll('button');
                    for (var i = 0; i < buttons.length; i++) {
                        var txt = buttons[i].innerText || buttons[i].textContent || '';
                        if (txt.toLowerCase().includes('create') || txt.toLowerCase().includes('start')) {
                            buttons[i].click();
                        }
                    }
                }
                """
                inject_js(js)
                
            time.sleep(1)
            
        if not detected_url:
            chrome_proc.terminate()
            raise RuntimeError(f"Timed out waiting for game creation on Table {idx+1}.")
            
        print(f"Room Created: {detected_url}. Authenticated session preserved.")
        print("Automatically configuring Game Settings via AppleScript JavaScript injection...")
        time.sleep(4) # Wait for room UI to load
        
        # Click Options
        inject_js("""
        var btns = document.querySelectorAll('button');
        for (var b of btns) {
            if (b.innerText.toUpperCase().includes('OPTIONS')) { b.click(); break; }
        }
        """)
        time.sleep(2)
        
        # Click Game Configurations
        inject_js("""
        var btns = document.querySelectorAll('button');
        for (var b of btns) {
            if (b.innerText.toUpperCase().includes('GAME CONFIGURATIONS')) { b.click(); break; }
        }
        """)
        time.sleep(2)
        
        # Click Yes on returning seat modal if it exists
        inject_js("""
        var btns = document.querySelectorAll('button');
        for (var b of btns) {
            if (b.innerText.toUpperCase() === 'YES') { b.click(); break; }
        }
        """)
        time.sleep(1)
        
        try:
            sb_cents = str(int(float(sb) * 100))
            bb_cents = str(int(float(bb) * 100))
        except ValueError:
            sb_cents = sb
            bb_cents = bb
            
        variant_map = {
            "nlh": "th",
            "plo": "omaha",
            "plo8": "plo8"
        }
        variant_value = variant_map.get(game_type.lower(), "th")
        
        # Configure everything!
        config_js = f"""
        function clickToggle(label, option) {{
            var divs = document.querySelectorAll('div, label, span');
            var target = null;
            for(var i = divs.length - 1; i >= 0; i--) {{
                if(!divs[i].innerText) continue;
                let txt = divs[i].innerText.trim();
                if(txt === label || (label.length > 5 && txt.includes(label))) {{
                    target = divs[i];
                    break;
                }}
            }}
            if(target) {{
                var container = target;
                for(var k=0; k<5; k++) {{
                    if(container && container.querySelectorAll('button').length > 0) break;
                    if(container) container = container.parentElement;
                }}
                if (container) {{
                    var btns = container.querySelectorAll('button');
                    for(var b of btns) {{
                        if(b.innerText.toUpperCase().trim() === option.toUpperCase()) {{
                            b.click();
                            return;
                        }}
                    }}
                }}
            }}
        }}

        function fillInput(label, value) {{
            var divs = document.querySelectorAll('div, label, span');
            var target = null;
            for(var i = divs.length - 1; i >= 0; i--) {{
                if(!divs[i].innerText) continue;
                let txt = divs[i].innerText.trim();
                if(txt === label || (label.length > 5 && txt.includes(label))) {{
                    target = divs[i];
                    break;
                }}
            }}
            if(target) {{
                var container = target;
                for(var k=0; k<5; k++) {{
                    if(container && container.querySelectorAll('input').length > 0) break;
                    if(container) container = container.parentElement;
                }}
                if (container) {{
                    var inp = container.querySelector('input');
                    if(inp) {{
                        inp.removeAttribute('disabled');
                        let setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                        setter.call(inp, value);
                        inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                }}
            }}
        }}

        clickToggle('Use cents values?', 'YES');
        
        // Set the poker variant
        var select = document.querySelector('select');
        if(select) {{
            select.value = '{variant_value}';
            select.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }}
        
        setTimeout(() => {{
            var sbInp = document.querySelector('input[placeholder="SB"]');
            if(sbInp) {{
                sbInp.removeAttribute('disabled');
                let setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                setter.call(sbInp, '{sb_cents}');
                sbInp.dispatchEvent(new Event('input', {{ bubbles: true }}));
            }}
            var bbInp = document.querySelector('input[placeholder="BB"]');
            if(bbInp) {{
                bbInp.removeAttribute('disabled');
                let setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                setter.call(bbInp, '{bb_cents}');
                bbInp.dispatchEvent(new Event('input', {{ bubbles: true }}));
            }}
            
            fillInput('Decision Time Limit', '20');
            fillInput('Time Bank Length', '60');
            fillInput('Number of played hands', '6');

            clickToggle('Allow Rebuy?', 'YES');
            clickToggle('Allow Run it Twice?', 'ASK PLAYERS');
            clickToggle('Showdown Presentation Time', 'FAST (3S)');
            clickToggle('Allow UTG Straddle', 'YES');
        }}, 500);
        """
        inject_js(config_js)
        time.sleep(3)
        
        # Change table title (Optional)
        title_js = f"""
        try {{
            var btns = document.querySelectorAll('button');
            for (var b of btns) {{
                if (b.innerText.toUpperCase().includes('CHANGE TABLE TITLE')) {{ b.click(); break; }}
            }}
            setTimeout(() => {{
                let titleInp = document.querySelector('input[placeholder="Table Title"]');
                if(!titleInp) {{
                    let inputs = document.querySelectorAll('input[type="text"]');
                    titleInp = inputs[inputs.length - 1];
                }}
                if(titleInp) {{
                    let setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                    setter.call(titleInp, "{game_type.upper()} Table {table_num}");
                    titleInp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                }}
                for (var b of document.querySelectorAll('button')) {{
                    if (b.innerText.toUpperCase().includes('UPDATE')) {{ b.click(); break; }}
                }}
            }}, 1000);
        }} catch(e) {{}}
        """
        if table_num:
            inject_js(title_js)
            time.sleep(3)
            
        # Click Update Game or Close
        inject_js("""
        var btns = document.querySelectorAll('button');
        for (var b of btns) {
            let txt = b.innerText.toUpperCase();
            if (txt.includes('START GAME') || txt.includes('UPDATE GAME') || txt === 'CLOSE' || (b.className && b.className.includes('modal-close'))) {
                b.click();
            }
        }
        // Fallback: press escape
        document.dispatchEvent(new KeyboardEvent('keydown', {'key': 'Escape'}));
        """)
        time.sleep(2)
        
        # Verify URL again just in case
        final_url = run_applescript('tell application "Google Chrome" to return URL of active tab of front window')
        print(f"Table configured successfully! Room URL: {final_url}")
        urls.append((table_info, final_url))
        
    print("\n============================================================")
    print(" ALL TABLES CREATED AND CONFIGURED!")
    print("============================================================\n")
    
    # Keep the final window open for a bit, then prompt user to manually close it when ready,
    # or just leave it open!
    print("Configuration complete! The Chrome window is still open for you to verify.")
    
    if urls:
        formatted_list = []
        for (table_info, url) in urls:
            if len(table_info) == 4:
                game_type, table_num, sb, bb = table_info
            else:
                game_type, table_num = table_info
                sb, bb = "0.25", "0.50"
            formatted_list.append(f"Table {table_num} - {game_type.upper()} <{url}>")
            
        final_text = "\n".join(formatted_list)
        print("Output for Email (Copied to clipboard):\n")
        print(final_text)
        
        # Save the created game details to a JSON file for the settlement script
        today = datetime.datetime.now()
        
        is_adhoc_run = "--adhoc" in sys.argv
        
        game_history = {
            "date": today.strftime("%Y-%m-%d"),
            "description": today.strftime("%m%d%y"),
            "game_ids": [url.split("/games/")[-1] for _, url in urls],
            "tables": [],
            "is_adhoc": is_adhoc_run
        }
        for (table_info, url) in urls:
            if len(table_info) == 4:
                g_type, t_num, g_sb, g_bb = table_info
            else:
                g_type, t_num = table_info
                g_sb, g_bb = "0.25", "0.50"
            game_history["tables"].append({
                "game_type": g_type, 
                "table_num": t_num, 
                "sb": g_sb, 
                "bb": g_bb, 
                "game_id": url.split("/games/")[-1]
            })
            
        try:
            with open("last_created_games.json", "w") as f:
                json.dump(game_history, f, indent=4)
            print("Saved game details to 'last_created_games.json' for settlement automation.")
        except Exception as e:
            print(f"Warning: Could not save last_created_games.json: {e}")
        
        process = subprocess.Popen('pbcopy', env={'LANG': 'en_US.UTF-8'}, stdin=subprocess.PIPE)
        process.communicate(final_text.encode('utf-8'))
        print("\n[SUCCESS] The URLs have been copied to your clipboard!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create Poker Now tables.")
    parser.add_argument("args", nargs="*")
    parser.add_argument("--config", type=str)
    parser.add_argument("--sb", type=str, default="0.25")
    parser.add_argument("--bb", type=str, default="0.50")
    
    parsed = parser.parse_args()
    args = parsed.args
    sb = parsed.sb
    bb = parsed.bb
    
    tables_to_create = []
    
    if parsed.config:
        try:
            config_data = json.loads(parsed.config)
            if isinstance(config_data, list):
                for details in config_data:
                    game_type = details.get("type", "nlh").lower()
                    table_num = len(tables_to_create) + 1
                    t_sb = str(details.get("sb", sb))
                    t_bb = str(details.get("bb", bb))
                    tables_to_create.append((game_type, table_num, t_sb, t_bb))
            elif isinstance(config_data, dict):
                for table_name, details in config_data.items():
                    game_type = details.get("game_type", "nlh")
                    table_num = len(tables_to_create) + 1
                    t_sb = str(details.get("sb", sb))
                    t_bb = str(details.get("bb", bb))
                    tables_to_create.append((game_type.lower(), table_num, t_sb, t_bb))
        except json.JSONDecodeError:
            print("Error parsing --config JSON.")
            sys.exit(1)
    else:
        allowed_types = ["nlh", "plo", "plo8"]
        if not args:
            tables_to_create.append(("nlh", 1, sb, bb))
        else:
            i = 0
            while i < len(args):
                arg = args[i].lower()
                if arg in allowed_types:
                    count = 1
                    if i + 1 < len(args) and args[i+1].isdigit():
                        count = int(args[i+1])
                        i += 2
                    else:
                        i += 1
                    
                    for _ in range(count):
                        table_num = len(tables_to_create) + 1
                        tables_to_create.append((arg, table_num, sb, bb))
                else:
                    print(f"Error: Unknown argument '{arg}'")
                    sys.exit(1)
                    
    run(tables_to_create)
