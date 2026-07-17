import subprocess

def run_js(js):
    escaped_js = js.replace('\\', '\\\\').replace('"', '\\"')
    applescript = f"""
    tell application "Google Chrome"
        set theResult to execute front window's active tab javascript "{escaped_js}"
        return theResult
    end tell
    """
    return subprocess.run(["osascript", "-e", applescript], capture_output=True, text=True).stdout

res = run_js("""
(function() {
    function findButtonNearText(labelText, buttonText) {
        var divs = document.querySelectorAll('div, label, span');
        var target = null;
        for(var i = divs.length - 1; i >= 0; i--) {
            if(divs[i].innerText && divs[i].innerText.includes(labelText)) {
                target = divs[i];
                break;
            }
        }
        if(target) {
            var container = target;
            while(container && container.querySelectorAll('button').length === 0) {
                container = container.parentElement;
            }
            if (container) {
                var btns = container.querySelectorAll('button');
                for(var b of btns) {
                    if(b.innerText.toUpperCase().trim() === buttonText.toUpperCase()) {
                        b.click();
                        return "Clicked " + buttonText;
                    }
                }
            }
        }
        return "Not found";
    }
    return findButtonNearText('Use cents values?', 'YES');
})();
""")
print("RES:", res)
