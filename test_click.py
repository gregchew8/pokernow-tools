import subprocess, time

def run_js(js):
    escaped_js = js.replace('\\', '\\\\').replace('"', '\\"')
    applescript = f"""
    tell application "Google Chrome"
        execute front window's active tab javascript "{escaped_js}"
    end tell
    """
    return subprocess.run(["osascript", "-e", applescript], capture_output=True, text=True).stdout

# Click OPTIONS
run_js("""
var btns = document.querySelectorAll('button');
for(var b of btns) { if(b.innerText.toUpperCase().includes('OPTIONS')) { b.click(); break; } }
""")

time.sleep(1)

# Dump buttons again
res = run_js("""
var btns = document.querySelectorAll('button');
var res = [];
for (var i=0; i<btns.length; i++) {
    res.push(btns[i].innerText);
}
res.join('|');
""")
print(res)
