import subprocess
js_inject = """
tell application "Google Chrome"
    execute front window's active tab javascript "
        (function() {
            var buttons = document.querySelectorAll('button');
            var res = [];
            for (var i = 0; i < buttons.length; i++) {
                res.push(buttons[i].innerText || buttons[i].textContent);
            }
            return res.join('|');
        })();
    "
end tell
"""
print("Buttons:", subprocess.run(["osascript", "-e", js_inject], capture_output=True, text=True).stdout.strip())
