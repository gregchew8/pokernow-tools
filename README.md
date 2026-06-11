# Poker Now Automation Tools

This repository contains a suite of Python scripts to automate setting up game rooms on Poker Now and calculating settlements from game cashout ledgers.

## Tools Overview

1. **Lobby Setup Automation** (`login.py` & `setup_poker_auth.py`)
   - Logs into your Poker Now owner lobby.
   - Automates the creation and configuration (blinds, variant types, timers) of multiple cash game tables in parallel.
   - Copies ready-to-share links and commands to the clipboard along with an email subject line.
2. **Core Settlement Engine** (`pokernow_settlement.py`)
   - Combines and processes player cashouts from ledgers.
   - Runs an optimization flow (using `or-tools` or `networkx` solvers) to resolve payouts with the minimum number of transactions.
   - Generates an HTML report output.
3. **Interactive Run Wrapper** (`run_settlement.py`)
   - Interactive wrapper that runs the settlement engine.
   - Prompts for date-based payment notes, processes pasted game links/email texts, and extracts game IDs.
   - Detects unrecognized player nicknames, prompts for their Venmo handle, appends it to `payment_info.csv` on the fly, and retries automatically.

---

## Installation & Setup

### 1. Prerequisites
Install Python 3 and the required libraries:
```bash
pip install playwright pandas requests networkx ortools
playwright install chromium
```

### 2. Login Setup (First Time Only)
Run `login.py` once to authenticate your Poker Now account and establish a persistent browser profile:
```bash
python login.py
```
- A headed Chromium browser will launch.
- Log in to your Poker Now account (e.g., via Google).
- Once logged in, press **Enter** in your terminal window to save the session locally in `./chrome-profile`.

---

## Usage

### Creating Poker Tables
Run `setup_poker_auth.py` with the count and variant combinations you want to host:
```bash
# General usage:
# python setup_poker_auth.py [variant] [count] [variant] [count] ...

# Example: Create 2 No-Limit Hold'em (NLH) tables and 1 Pot-Limit Omaha (PLO) table:
python setup_poker_auth.py nlh 2 plo 1
```
The script will output table tokens/URLs and copy formatted email links to your clipboard.

### Running Settlements Interactively
When games are over, execute `run_settlement.py` to calculate final payouts:
```bash
python run_settlement.py
```
- **Step 1**: Confirm or enter the description note (e.g. `061026` for June 10, 2026).
- **Step 2**: Paste the email text or game links. Press **Enter** twice to complete.
- **Step 3**: Press **Enter** to confirm the games are finished.
- **Step 4**: The script downloads the ledgers and runs the settlement. If an unrecognized nickname is found, it will prompt you for their Venmo handle, append it to `payment_info.csv`, and automatically retry.

---

## Configuration & Security

- **`payment_info.csv`**: Maps player aliases on Poker Now (`PN Alias`) to Venmo handles (`Venmo / other`).
- **⚠️ Personal Data**: Do **NOT** publish `payment_info.csv` or the `chrome-profile/` directory to public repositories. They are excluded by `.gitignore`.
