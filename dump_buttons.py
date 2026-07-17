import subprocess

applescript = """
tell application "Google Chrome"
    execute front window's active tab javascript "
        var btns = document.querySelectorAll('button');
        var res = [];
        for (var i=0; i<btns.length; i++) {
            res.push(btns[i].innerText);
        }
        res.join('|');
    "
end tell
"""
res = subprocess.run(["osascript", "-e", applescript], capture_output=True, text=True)
print(res.stdout)
