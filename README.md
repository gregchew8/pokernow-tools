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
3. **Game Announcer** (`announce_games.py` & `update_calendar.py`)
   - Automatically runs table setups based on the day's config in `schedule.json`.
   - Sends rich email announcements to Google Groups.
   - Creates/updates game entries dynamically in Google Calendar.
4. **Auto Settlement Engine** (`auto_settle.py` & `pokernow_settlement.py`)
   - Automatically runs morning calculations, downloads cashout CSVs, optimizes transactions, generates HTML reports, and emails payouts.
5. **Replication Script** (`sync_to_drive.sh`)
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

### 4. Scheduler Installation
Register the launchd agents for automated execution:
```bash
python3 setup_local_scheduler.py
```
- Game announcements trigger automatically at **5:00 PM** (Mon, Wed, Fri, Sat).
- Settlements run automatically at **8:00 AM** (Tue, Thu, Sat, Sun).

---

## Configuration & Security

- **`schedule.json`**: Configures specific game formats, blinds, and tables for each weekday.
- **`.env`**: Stores secure SMTP settings, Google Sheet CSV URL, Discord Webhook, and Google Calendar ID.
- **`payment_info.csv`**: Maps player aliases on Poker Now (`PN Alias`) to Venmo handles.
- **⚠️ Personal Data**: Do **NOT** publish `.env`, `calendar_credentials.json`, `payment_info.csv` or the `chrome-profile/` directory to public repositories. They are excluded by `.gitignore`.
