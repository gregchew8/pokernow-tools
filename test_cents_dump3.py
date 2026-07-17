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
var divs = document.querySelectorAll('div, label, span');
var target = null;
for(var i=0; i<divs.length; i++) {
    if(divs[i].innerText && divs[i].innerText.toLowerCase().includes('cents') && divs[i].innerText.length < 30) {
        target = divs[i].parentElement;
        break;
    }
}
if(target) {
    var btns = target.querySelectorAll('button');
    var res = [];
    for(var b of btns) res.push(b.innerText);
    "Text=" + target.innerText.replace('\\n', ' ') + " | Buttons=" + res.join(',');
} else 'NOT FOUND';
""")
print(res)
