#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.parse

PORT = 8080
WORKING_DIR = "/Users/gregchew/pokernow"

# Thread-safe status trackers for running subprocesses
status_lock = threading.Lock()
running_tasks = {
    "announcer": False,
    "settlement": False
}

def run_script_in_background(task_name, cmd):
    global running_tasks
    with status_lock:
        if running_tasks[task_name]:
            return False
        running_tasks[task_name] = True
        
    def worker():
        try:
            print(f"[WebUI] Launching background task: {task_name} -> {' '.join(cmd)}")
            # Run the command and wait for it to complete
            subprocess.run(cmd, cwd=WORKING_DIR, check=True)
            print(f"[WebUI] Task {task_name} finished successfully.")
        except Exception as e:
            print(f"[WebUI] Error running task {task_name}: {e}")
        finally:
            with status_lock:
                running_tasks[task_name] = False
                
    t = threading.Thread(target=worker)
    t.daemon = True
    t.start()
    return True

def get_last_log_lines(filepath, num_lines=30):
    if not os.path.exists(filepath):
        return "No log file found yet."
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
            return "".join(lines[-num_lines:])
    except Exception as e:
        return f"Error reading log file: {e}"

class WebUIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence standard HTTP requests logging in stdout
        pass

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(self.get_html_dashboard().encode("utf-8"))
        elif self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            
            # Load last created games
            last_games = {}
            games_json_path = os.path.join(WORKING_DIR, "last_created_games.json")
            if os.path.exists(games_json_path):
                try:
                    with open(games_json_path, "r") as f:
                        last_games = json.load(f)
                except:
                    pass

            with status_lock:
                status = {
                    "announcer_running": running_tasks["announcer"],
                    "settlement_running": running_tasks["settlement"],
                    "last_games": last_games,
                    "announcer_stdout": get_last_log_lines(os.path.join(WORKING_DIR, "output/game_nights_stdout.log")),
                    "announcer_stderr": get_last_log_lines(os.path.join(WORKING_DIR, "output/game_nights_stderr.log")),
                    "settlement_stdout": get_last_log_lines(os.path.join(WORKING_DIR, "output/next_morning_stdout.log")),
                    "settlement_stderr": get_last_log_lines(os.path.join(WORKING_DIR, "output/next_morning_stderr.log")),
                }
            self.wfile.write(json.dumps(status).encode("utf-8"))
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        if self.path == "/api/run-announcer":
            cmd = [sys.executable, "announce_games.py"]
            success = run_script_in_background("announcer", cmd)
            self.send_response(200 if success else 409)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success}).encode("utf-8"))
        elif self.path == "/api/run-settlement":
            cmd = [sys.executable, "auto_settle.py", "--force"]
            success = run_script_in_background("settlement", cmd)
            self.send_response(200 if success else 409)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success}).encode("utf-8"))
        else:
            self.send_error(404, "Not Found")

    def get_html_dashboard(self):
        return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Poker Now Control Panel</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0b0f19;
            --card-bg: rgba(22, 28, 45, 0.7);
            --border-color: rgba(255, 255, 255, 0.08);
            --text-color: #e2e8f0;
            --text-muted: #94a3b8;
            --primary: #4f46e5;
            --primary-hover: #6366f1;
            --success: #10b981;
            --danger: #ef4444;
            --glow: 0 0 20px rgba(79, 70, 229, 0.15);
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg-color);
            background-image: 
                radial-gradient(at 0% 0%, rgba(31, 41, 55, 0.3) 0, transparent 50%),
                radial-gradient(at 50% 0%, rgba(79, 70, 229, 0.05) 0, transparent 50%);
            color: var(--text-color);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 2rem 1rem;
        }

        .container {
            width: 100%;
            max-width: 900px;
            display: flex;
            flex-direction: column;
            gap: 2rem;
        }

        header {
            text-align: center;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--border-color);
        }

        h1 {
            font-size: 2.2rem;
            font-weight: 800;
            letter-spacing: -0.05em;
            background: linear-gradient(135deg, #fff 0%, #a5b4fc 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }

        .subtitle {
            color: var(--text-muted);
            font-size: 1rem;
        }

        .dashboard-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 1.5rem;
        }

        @media (min-width: 768px) {
            .dashboard-grid {
                grid-template-columns: 1fr 1fr;
            }
            .full-width {
                grid-column: span 2;
            }
        }

        .card {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem;
            backdrop-filter: blur(12px);
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }

        .card:hover {
            transform: translateY(-2px);
            box-shadow: var(--glow);
            border-color: rgba(79, 70, 229, 0.3);
        }

        h2 {
            font-size: 1.25rem;
            font-weight: 600;
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .status-badge {
            font-size: 0.75rem;
            padding: 0.25rem 0.6rem;
            border-radius: 20px;
            font-weight: 600;
            text-transform: uppercase;
        }

        .status-idle {
            background-color: rgba(148, 163, 184, 0.15);
            color: var(--text-muted);
            border: 1px solid rgba(148, 163, 184, 0.2);
        }

        .status-running {
            background-color: rgba(16, 185, 129, 0.15);
            color: var(--success);
            border: 1px solid rgba(16, 185, 129, 0.2);
            animation: pulse 1.5s infinite;
        }

        @keyframes pulse {
            0% { opacity: 0.6; }
            50% { opacity: 1; }
            100% { opacity: 0.6; }
        }

        .btn {
            display: block;
            width: 100%;
            padding: 0.8rem 1.5rem;
            font-size: 1rem;
            font-weight: 600;
            color: #fff;
            background: linear-gradient(135deg, var(--primary) 0%, #312e81 100%);
            border: none;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s ease;
            text-align: center;
            margin-top: 1rem;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }

        .btn:hover {
            background: linear-gradient(135deg, var(--primary-hover) 0%, var(--primary) 100%);
            transform: translateY(-1px);
        }

        .btn:disabled {
            background: #1e293b;
            color: var(--text-muted);
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }

        .games-list {
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
            margin-top: 0.5rem;
        }

        .game-item {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 8px;
            padding: 0.75rem 1rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .game-title {
            font-weight: 600;
            font-size: 0.95rem;
        }

        .game-link {
            font-size: 0.85rem;
            color: var(--primary-hover);
            text-decoration: none;
            border: 1px solid rgba(99, 102, 241, 0.2);
            padding: 0.25rem 0.6rem;
            border-radius: 4px;
            transition: all 0.2s;
        }

        .game-link:hover {
            background: rgba(99, 102, 241, 0.1);
            border-color: var(--primary-hover);
        }

        .console-container {
            margin-top: 1rem;
        }

        .console-header {
            font-size: 0.85rem;
            color: var(--text-muted);
            margin-bottom: 0.25rem;
            font-weight: 600;
        }

        pre {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.8rem;
            background: #020617;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 1rem;
            max-height: 250px;
            overflow-y: auto;
            white-space: pre-wrap;
            word-break: break-all;
            color: #34d399;
        }

        .error-log pre {
            color: #f87171;
        }
        
        .no-games {
            color: var(--text-muted);
            font-style: italic;
            text-align: center;
            padding: 1rem 0;
            font-size: 0.95rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Poker Now Control Panel</h1>
            <p class="subtitle">Tailscale Secure Remote Management</p>
        </header>

        <div class="dashboard-grid">
            <!-- Game Announcer Card -->
            <div class="card">
                <h2>
                    <span>Game Announcer</span>
                    <span id="announcer-badge" class="status-badge status-idle">Idle</span>
                </h2>
                <p class="subtitle">Launches room creations & sends email announcements based on today's schedule config.</p>
                <button id="btn-announcer" class="btn" onclick="triggerTask('announcer')">Start Table Setup</button>
            </div>

            <!-- Settlement Card -->
            <div class="card">
                <h2>
                    <span>Payout Settlement</span>
                    <span id="settlement-badge" class="status-badge status-idle">Idle</span>
                </h2>
                <p class="subtitle">Manually downloads cashout logs for current tables, runs payouts optimization, and emails results.</p>
                <button id="btn-settlement" class="btn" onclick="triggerTask('settlement')">Run Manual Settlement</button>
            </div>

            <!-- Active Games Card -->
            <div class="card full-width">
                <h2>Active Game Tables <span id="active-date" style="font-size: 0.85rem; color: var(--text-muted);"></span></h2>
                <div id="active-games-container" class="games-list">
                    <!-- Loaded dynamically -->
                </div>
            </div>

            <!-- Logs Section -->
            <div class="card full-width">
                <h2>System Logs & Outputs</h2>
                
                <div class="console-container">
                    <div class="console-header">Announcer Logs (Stdout)</div>
                    <pre id="announcer-stdout">Loading logs...</pre>
                </div>
                
                <div class="console-container error-log">
                    <div class="console-header">Announcer Errors (Stderr)</div>
                    <pre id="announcer-stderr">Loading logs...</pre>
                </div>
                
                <hr style="margin: 2rem 0; border: none; border-top: 1px solid var(--border-color);">
                
                <div class="console-container">
                    <div class="console-header">Settlement Logs (Stdout)</div>
                    <pre id="settlement-stdout">Loading logs...</pre>
                </div>
                
                <div class="console-container error-log">
                    <div class="console-header">Settlement Errors (Stderr)</div>
                    <pre id="settlement-stderr">Loading logs...</pre>
                </div>
            </div>
        </div>
    </div>

    <script>
        function updateDashboard() {
            fetch('/api/status')
                .then(res => res.json())
                .then(data => {
                    // Update Announcer Status
                    const announcerBadge = document.getElementById('announcer-badge');
                    const btnAnnouncer = document.getElementById('btn-announcer');
                    if (data.announcer_running) {
                        announcerBadge.textContent = 'Running';
                        announcerBadge.className = 'status-badge status-running';
                        btnAnnouncer.disabled = true;
                        btnAnnouncer.textContent = 'Setting up Tables...';
                    } else {
                        announcerBadge.textContent = 'Idle';
                        announcerBadge.className = 'status-badge status-idle';
                        btnAnnouncer.disabled = data.settlement_running;
                        btnAnnouncer.textContent = 'Start Table Setup';
                    }

                    // Update Settlement Status
                    const settlementBadge = document.getElementById('settlement-badge');
                    const btnSettlement = document.getElementById('btn-settlement');
                    if (data.settlement_running) {
                        settlementBadge.textContent = 'Running';
                        settlementBadge.className = 'status-badge status-running';
                        btnSettlement.disabled = true;
                        btnSettlement.textContent = 'Calculating Payouts...';
                    } else {
                        settlementBadge.textContent = 'Idle';
                        settlementBadge.className = 'status-badge status-idle';
                        btnSettlement.disabled = data.announcer_running;
                        btnSettlement.textContent = 'Run Manual Settlement';
                    }

                    // Update Logs
                    document.getElementById('announcer-stdout').textContent = data.announcer_stdout;
                    document.getElementById('announcer-stderr').textContent = data.announcer_stderr;
                    document.getElementById('settlement-stdout').textContent = data.settlement_stdout;
                    document.getElementById('settlement-stderr').textContent = data.settlement_stderr;

                    // Update Active Games
                    const activeContainer = document.getElementById('active-games-container');
                    const activeDate = document.getElementById('active-date');
                    activeContainer.innerHTML = '';
                    
                    if (data.last_games && data.last_games.tables && data.last_games.tables.length > 0) {
                        activeDate.textContent = `(Game Date: ${data.last_games.date})`;
                        data.last_games.tables.forEach(t => {
                            const item = document.createElement('div');
                            item.className = 'game-item';
                            
                            const title = document.createElement('span');
                            title.className = 'game-title';
                            const stakes = (t.sb && t.bb) ? ` (${t.sb}/${t.bb})` : '';
                            title.textContent = `${t.game_type.toUpperCase()}${stakes} - Table ${t.table_num}`;
                            
                            const link = document.createElement('a');
                            link.className = 'game-link';
                            link.href = `https://www.pokernow.club/games/${t.game_id}`;
                            link.target = '_blank';
                            link.textContent = 'Open Room';
                            
                            item.appendChild(title);
                            item.appendChild(link);
                            activeContainer.appendChild(item);
                        });
                    } else {
                        activeDate.textContent = '';
                        activeContainer.innerHTML = '<div class="no-games">No active tables found. Click "Start Table Setup" to create them.</div>';
                    }
                })
                .catch(err => console.error("Error updating dashboard:", err));
        }

        function triggerTask(taskName) {
            const endpoint = taskName === 'announcer' ? '/api/run-announcer' : '/api/run-settlement';
            
            // Optimistically disable buttons
            document.getElementById('btn-announcer').disabled = true;
            document.getElementById('btn-settlement').disabled = true;

            fetch(endpoint, { method: 'POST' })
                .then(res => {
                    if (res.ok) {
                        updateDashboard();
                    } else {
                        alert("Failed to start task. Task is already running or conflict occurred.");
                    }
                })
                .catch(err => {
                    alert("Error triggering task: " + err);
                    updateDashboard();
                });
        }

        // Periodically refresh dashboard every 2 seconds
        setInterval(updateDashboard, 2000);
        updateDashboard();
    </script>
</body>
</html>
"""

def main():
    server_address = ("", PORT)
    httpd = HTTPServer(server_address, WebUIHandler)
    print(f"[WebUI] Server running at http://localhost:{PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("[WebUI] Stopping server...")
        httpd.server_close()

if __name__ == "__main__":
    main()
