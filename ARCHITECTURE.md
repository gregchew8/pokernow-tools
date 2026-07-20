# System Architecture & Flow

This document details the system design, process execution boundaries, and network flows for the Poker Now Automation and Analytics suite.

---

## Architecture Schematic

```text
+-----------------------------------------------------------------------------------+
|                              ADMIN BROWSER / CLIENT                               |
+-----------------------------------------------------------------------------------+
                                         |
                                  (HTTPS Requests)
                                         v
+-----------------------------------------------------------------------------------+
|                                  RAILWAY CLOUD                                    |
|                                                                                   |
|  +-----------------------+              +-----------------------+                 |
|  |   Railway Cloud UI    | <----------> |  Railway PostgreSQL   |                 |
|  |    (cloud_ui.py)      |  (Queries)   |      (Database)       |                 |
|  +-----------------------+              +-----------------------+                 |
|         |          |                                                              |
|   (Serve   (Dynamic Fetch                                                         |
|    HTML)    of csv mapping)                                                       |
|         |          |                                                              |
+---------|----------|--------------------------------------------------------------+
          |          v                                                               
          |  +-----------------------+                                               
          |  |  Google Sheets CSV    |                                               
          |  +-----------------------+                                               
          v                                                                         
  [ Renders Instantly ]                                                             
          |                                                                         
          | (Only proxy for OTP emails / local script execution)                    
          v                                                                         
+-----------------------------------------------------------------------------------+
|                                  LOCAL MAC MINI                                   |
|                                                                                   |
|  +-----------------------------------+   +-------------------------------------+  |
|  |       Local Agent Daemon          |   |      Local Control Panel            |  |
|  |     (local_agent.py - 8081)       |   |       (web_ui.py - 8080)            |  |
|  +-----------------------------------+   +-------------------------------------+  |
|         |                   |                                                     |
|    (Sends OTP)      (Saves schedule.json                                          |
|         |           & reloads plists)                                             |
|         v                   v                                                     |
|  +--------------+   +----------------------------------------------------------+  |
|  |  Local SMTP  |   |             macOS launchd (System Daemon)                |  |
|  | (Gmail Relay)|   |   Reads calendar plists (game_nights / next_morning)     |  |
|  +--------------+   +----------------------------------------------------------+  |
|                                     |                                             |
|                                     | (Fires at Scheduled Calendar Times)         |
|                                     v                                             |
|                     +--------------------------------------------+                |
|                     |        Execution Automation Scripts        |                |
|                     |  - Setup & Announce: announce_games.py     |                |
|                     |  - Download & Settle: auto_settle.py       |                |
|                     +--------------------------------------------+                |
+-----------------------------------------------------------------------------------+
```

---

## Active Port Mapping

| Port | Service | Location | Description |
|---|---|---|---|
| **8080** | Railway Cloud UI (`cloud_ui.py`) | **Railway Cloud** | Authenticated admin gateway (`poker.gchew.com`). Serves dashboard & analytics. |
| **8081** | Local Agent (`local_agent.py`) | **Mac Mini (Local)** | Responds to proxied commands, performs SMTP relays, and runs local execution scripts. |
| **8080** | Local Dashboard (`web_ui.py`) | **Mac Mini (Local)** | *(Optional)* Starts manually only if local offline browser administration is required. |

---

## Execution Boundaries

### 1. What Railway Handles (Heavy Lift)
- **Session Authentication (OTP & Expiry)**: Manages secure access controls for admins.
- **HTML Layout Compilation**: Renders the complete web structures for the control dashboard and player analytics.
- **Relational Data Processing**: Queries Postgres and downloads live alias mappings from the Google Sheets CSV URL. Calculates net profits, averages, trajectory datasets, and sorts tables.
- **Session Deletion & Database Management**: Handles the API route for deleting specific session dates and purging associated player metrics, automatically triggering dashboard recalculation.

### 2. What the Mac Mini Handles (Hardware & Security Constraints)
- **Local Browser Automation (Playwright / AppleScript)**: Creates Poker Now rooms, toggles configurations, parses table logs, and downloads CSV ledgers. (Must run on physical host due to Turnstile Cloudflare bypass mechanics).
- **Outbound Email Relay (SMTP)**: Routes OTP and settlement emails via local ISP network (bypassing Railway's outbound SMTP block).
- **Cron Scheduling (`launchd`)**: Triggers automated announcer runs at 5:00 PM and automated settlements at 8:00 AM.

---

## Secure Admin PIN Layer

To prevent casual eyes from inspecting administrative operations or activity logs, the dashboard integrates a modular secure locking system:

```text
[ ADMIN_PIN (config) ] --(SHA-256 Hash)--> [ HTML Template replacement ]
                                                       |
                                                       v
[ Entered PIN string ] --(SHA-256 Hash)--> [ Browser validation comparison ]
                                                       |
                  +------------------------------------+------------------------------------+
                  | Match                                                                   | Mismatch
                  v                                                                         v
   [ Remove .admin-locked CSS class ]                                        [ Display "Invalid PIN" ]
   [ sessionStorage.admin_unlocked = true ]                                  [ Reset and focus input ]
```

- **Hashing Security**: The PIN is hashed using SHA-256 on the server-side (`hashlib`) before being injected into the HTML response. The user's input is hashed in-browser via the Web Cryptography API (`crypto.subtle.digest`). The raw PIN is never transmitted in cleartext or saved in the JavaScript source.
- **Tailored Locking**: Any element containing the `admin-only` CSS class is hidden automatically when the page wrapper has the `admin-locked` class active. Unlocking the page cleanses the class, revealing logs and advanced developer options.

---

## Historical Settlements Backfill Flow

When importing older games where Poker Now logs are unavailable but raw transaction payouts were posted to Google Groups:

1. **Scraping**: A tab-spawning Javascript console script extracts the topic body and post dates, saving them to `settlements.json`.
2. **Parsing**: The `import_text_settlements.py` script parses winner requests and payer transactions using regular expressions.
3. **Reconciliation**: Player nets are calculated in cents:
   - Winners: `net += win_amount`
   - Payers: `net -= payment_amount`
   Verify that `sum(player_nets) == 0` (zero-sum check).
4. **Duplicate Filtering**: Compares the session date against existing database entries. If new, it creates a dummy session file and inserts the calculated player net profits into the database.
