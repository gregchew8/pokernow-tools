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
var html = '';
for(var i=0; i<inps.length; i++) {
    if(inps[i].value === '0.10' || inps[i].value === '10') {
        var c = inps[i];
        for(var k=0; k<3; k++) { if(c.parentElement) c = c.parentElement; }
        html = c.innerHTML;
        break;
    }
}
html;
""")
print(res)
