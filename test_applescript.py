import subprocess

js_inject = """
tell application "Google Chrome"
    execute front window's active tab javascript "
        (function() {
            try {
                var input = document.querySelector('input[type=\\"text\\"]');
                if (input && !input.value) {
                    var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, \\"value\\").set;
                    nativeInputValueSetter.call(input, 'Dealer');
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    return 'input filled';
                } else {
                    var buttons = document.querySelectorAll('button');
                    for (var i = 0; i < buttons.length; i++) {
                        var txt = buttons[i].innerText || buttons[i].textContent || '';
                        if (txt.toLowerCase().includes('start')) {
                            buttons[i].click();
                            return 'button clicked';
                        }
                    }
                    return 'button not found';
                }
            } catch (e) {
                return 'ERROR: ' + e.toString();
            }
        })();
    "
end tell
"""

res = subprocess.run(["osascript", "-e", js_inject], capture_output=True, text=True)
print("JS Result:", res.stdout.strip())
print("JS Error:", res.stderr.strip())
