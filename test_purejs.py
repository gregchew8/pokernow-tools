import subprocess

def run_js(js):
    escaped_js = js.replace('\\', '\\\\').replace('"', '\\"')
    applescript = f"""
    tell application "Google Chrome"
        execute front window's active tab javascript "{escaped_js}"
    end tell
    """
    return subprocess.run(["osascript", "-e", applescript], capture_output=True, text=True).stdout

# Click Game Configurations
run_js("""
var btns = document.querySelectorAll('button');
for(var b of btns) { if(b.innerText.toUpperCase().includes('GAME CONFIGURATIONS')) { b.click(); break; } }
""")

# Test my pure JS toggler
res = run_js("""
(function() {
    function clickToggle(label, option) {
        var divs = document.querySelectorAll('div, label, span');
        var target = null;
        for(var i = divs.length - 1; i >= 0; i--) {
            if(!divs[i].innerText) continue;
            let txt = divs[i].innerText.trim();
            if(txt === label || (label.length > 5 && txt.includes(label))) {
                target = divs[i];
                break;
            }
        }
        if(target) {
            var container = target;
            for(var k=0; k<5; k++) {
                if(container && container.querySelectorAll('button').length > 0) break;
                if(container) container = container.parentElement;
            }
            if (container) {
                var btns = container.querySelectorAll('button');
                for(var b of btns) {
                    if(b.innerText.toUpperCase().trim() === option.toUpperCase()) {
                        b.click();
                        return "Clicked " + option;
                    }
                }
            }
        }
        return "Not found";
    }
    return clickToggle('Use cents values?', 'YES');
})();
""")
print("Res:", res)
