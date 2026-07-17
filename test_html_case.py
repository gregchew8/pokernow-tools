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
var btns = document.querySelectorAll('button');
var res = [];
for (var i=0; i<btns.length; i++) {
    if(btns[i].innerText.toUpperCase() === 'YES') {
        res.push(btns[i].innerHTML);
    }
}
res.join('|');
""")
print("HTML for YES buttons:", res)
