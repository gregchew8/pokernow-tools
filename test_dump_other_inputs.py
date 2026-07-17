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
var inps = document.querySelectorAll('input');
var res = [];
for(var i=0; i<inps.length; i++) {
    res.push(inps[i].outerHTML);
}
res.join('\\n');
""")
print(res)
