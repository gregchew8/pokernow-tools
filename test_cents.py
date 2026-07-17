import subprocess, time

def run_js(js):
    escaped_js = js.replace('\\', '\\\\').replace('"', '\\"')
    applescript = f"""
    tell application "Google Chrome"
        execute front window's active tab javascript "{escaped_js}"
    end tell
    """
    return subprocess.run(["osascript", "-e", applescript], capture_output=True, text=True).stdout

# Find and click
res = run_js("""
var btn = document.evaluate("//text()[contains(., 'Use cents')]/following::button[normalize-space()='YES'][1]", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
if (btn) {
    btn.click();
    btn.outerHTML;
} else {
    "NOT FOUND";
}
""")
print("Result:", res)
