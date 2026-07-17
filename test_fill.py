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
(function() {
    var divs = document.querySelectorAll('div, label, span');
    var target = null;
    for(var i = divs.length - 1; i >= 0; i--) {
        if(divs[i].innerText && divs[i].innerText.trim() === 'SB') {
            target = divs[i];
            break;
        }
    }
    if(target) {
        var container = target;
        for(var k=0; k<5; k++) {
            if(container && container.querySelectorAll('input').length > 0) break;
            if(container) container = container.parentElement;
        }
        if (container) {
            var inputs = container.querySelectorAll('input');
            return "Found inputs: " + inputs.length;
        }
    }
    return "Not found";
})();
""")
print("Res:", res)
