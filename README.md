# Poker Now Automation Tools

This repository contains a suite of Python scripts to automate setting up game rooms on Poker Now, announcing tables to Google Calendar/Groups/Discord, and calculating settlements from game cashout ledgers.

All active automation runs locally out of your SSD folder (e.g. `~/pokernow`), and replicates changes to Google Drive via a slave replica sync.

---

## Tools Overview

1. **Lobby Setup Automation** (`login.py` & `setup_poker_auth.py`)
   - Logs into your Poker Now owner lobby.
   - Automates the creation and configuration (blinds, variant types, timers, stakes) of multiple cash game tables in parallel.
   - Copies ready-to-share links and commands to the clipboard along with an email subject line.
   - Persists Playwright browser binaries in `./playwright-browsers` to protect against macOS cache cleanups.
2. **Automated Scheduler** (`setup_local_scheduler.py`)
   - Configures macOS `launchd` CalendarIntervals to run game setup and settlement calculations automatically.
   - Registers a persistent Web UI dashboard daemon to run on boot.
3. **Game Announcer** (`announce_games.py` & `update_calendar.py`)
   - Automatically runs table setups based on the day's config in `schedule.json`.
   - Sends rich email announcements to Google Groups.
   - Creates/updates game entries dynamically in Google Calendar.
4. **Auto Settlement Engine** (`auto_settle.py` & `pokernow_settlement.py`)
   - Automatically runs morning calculations, downloads cashout CSVs, optimizes transactions, generates HTML reports, and emails payouts.
5. **Remote Web UI Control Panel** (`web_ui.py`)
   - Serves a secure, zero-dependency local dashboard on port `8080` (accessible over Tailscale).
   - Allows triggering announcer and settlement scripts manually with log outputs visible in real time.
   - **Diagnostic Advisor**: Automatically parses and triages stdout/stderr outputs to identify common issues (e.g., SMTP auth failures, missing Playwright executables, missing player mappings) and displays clear recovery steps.
   - **Active vs. Stale Log Tracking**: Extracts execution and error timestamps to label error boxes with status badges (`[ACTIVE ERROR]`, `[STALE / RESOLVED]`, or `[SUCCESS]`). Stale/old error panels are dimmed with hover-reveal styling to prevent confusion.
   - **Clipboard Shortcuts**: Copy buttons next to each console log panel allow for quick sharing/debugging of stack traces.
6. **Replication Script** (`sync_to_drive.sh`)
   - Replicates local changes and logs back to your Google Drive backup.

---

## Installation & Setup

### 1. Prerequisites
Install Python 3 and the required libraries:
```bash
pip install playwright pandas requests networkx ortools
```

### 2. Persistent Playwright Browser
Set custom environment path and install Playwright Chromium directly into the workspace:
```bash
PLAYWRIGHT_BROWSERS_PATH=./playwright-browsers python3 -m playwright install chromium
```

### 3. Login Setup (First Time Only)
Run `login.py` once to authenticate your Poker Now account and establish a persistent browser profile:
```bash
python3 login.py
```
- A headed Chromium browser will launch.
- Log in to your Poker Now account (e.g., via Google).
- Once logged in, press **Enter** in your terminal window to save the session locally in `./chrome-profile`.

### 4. Scheduler & Web UI Installation
Register the launchd agents for automated execution and remote-control UI:
```bash
python3 setup_local_scheduler.py
```
- **Web UI Control Panel**: Starts immediately and runs in the background on port `8080` (access via `http://<tailscale-ip>:8080` when on Tailscale).
- **Game Announcements**: Triggers automatically at **5:00 PM** (Mon, Wed, Fri, Sat).
- **Settlements**: Runs automatically at **8:00 AM** (Tue, Thu, Sat, Sun).

---

## Configuration & Security

- **`schedule.json`**: Configures specific game formats, blinds, and tables for each weekday.
- **`.env`**: Stores secure SMTP settings, Google Sheet CSV URL, Discord Webhook, and Google Calendar ID.
- **`payment_info.csv`**: Maps player aliases on Poker Now (`PN Alias`) to Venmo handles.
- **Email Notification Branding**: Automated emails are sent with the display name `LCR Admins` and include a built-in feedback footer directing questions, suggestions, or improvements to `lcr-poker-admins@googlegroups.com`.
- **⚠️ Personal Data**: Do **NOT** publish `.env`, `calendar_credentials.json`, `payment_info.csv` or the `chrome-profile/` directory to public repositories. They are excluded by `.gitignore`.

