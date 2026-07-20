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

### 2. What the Mac Mini Handles (Hardware & Security Constraints)
- **Local Browser Automation (Playwright / AppleScript)**: Creates Poker Now rooms, toggles configurations, parses table logs, and downloads CSV ledgers. (Must run on physical host due to Turnstile Cloudflare bypass mechanics).
- **Outbound Email Relay (SMTP)**: Routes OTP and settlement emails via local ISP network (bypassing Railway's outbound SMTP block).
- **Cron Scheduling (`launchd`)**: Triggers automated announcer runs at 5:00 PM and automated settlements at 8:00 AM.
