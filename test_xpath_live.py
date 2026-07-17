import subprocess

def run_js(js):
    escaped_js = js.replace('\\', '\\\\').replace('"', '\\"')
    applescript = f"""
    tell application "Google Chrome"
        execute front window's active tab javascript "{escaped_js}"
    end tell
    """
    return subprocess.run(["osascript", "-e", applescript], capture_output=True, text=True).stdout

res = run_js("""
var btn1 = document.evaluate("//text()[contains(., 'Use cents')]/following::button[normalize-space()='YES'][1]", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
var btn2 = document.evaluate("//*[contains(text(), 'Use cents')]/following::button[contains(., 'YES')][1]", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;

(btn1 ? "btn1 found" : "btn1 null") + " | " + (btn2 ? "btn2 found" : "btn2 null");
""")
print(res)
