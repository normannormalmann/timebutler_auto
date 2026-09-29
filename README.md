# Timebutler Auto-Punch

[![CI](https://github.com/normannormalmann/timebutler_auto/actions/workflows/ci.yml/badge.svg)](https://github.com/normannormalmann/timebutler_auto/actions/workflows/ci.yml)

Automated time tracking for [Timebutler](https://app.timebutler.com/): the tool logs in and "punches in" (starts time recording) automatically whenever you are connected to specific Wi-Fi networks — e.g. your office Wi-Fi. It runs silently in the background, at most once per day.

> **New: [n8n mode](#n8n-mode-no-pc-required)** — runs on a server instead of your PC and covers the whole day: punch in between 09:00 and 09:30, a 30-minute break, and punch out 7.5–9 hours later.

**How it works (Windows mode):** a Windows scheduled task starts the script at sign-in and on every Wi-Fi (re)connect. The script checks your current SSID against an allowlist, and if it matches — and you haven't punched in today — it opens a headless browser, logs in and starts the time recorder.

## Contents

- [Quick Start](#quick-start)
- [Manual Installation](#manual-installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Autostart (Windows Task Scheduler)](#autostart-windows-task-scheduler)
- [n8n Mode (no PC required)](#n8n-mode-no-pc-required)
- [Troubleshooting](#troubleshooting)
- [Features](#features)
- [Development](#development)

## Quick Start

The interactive installer sets up everything in one go (available in **English** and **German**):

1. Open **PowerShell as Administrator**.
2. Clone and run:

   ```powershell
   git clone https://github.com/normannormalmann/timebutler_auto.git
   cd timebutler_auto
   .\install.ps1
   ```

The installer walks you through:

- **Credentials** — your Timebutler email and password (stored DPAPI-encrypted in the Windows Credential Manager).
- **Networks** — detects your current Wi-Fi and lets you pick the allowed networks from your saved profiles.
- **Environment** — checks for Python (offers to install it via Winget), creates a virtual environment, installs dependencies and the Playwright browser.
- **Task registration** — registers the scheduled task with both triggers (sign-in and Wi-Fi connect) so the script runs automatically.

When it finishes, verify the setup:

```powershell
python timebutler_run.py --status
```

That's it. If you prefer to set things up by hand, read on.

## Manual Installation

Prerequisites: **Python 3.8+** on Windows.

```bash
git clone https://github.com/normannormalmann/timebutler_auto.git
cd timebutler_auto

# virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate

# dependencies
pip install -r requirements.txt
playwright install chromium
```

Then configure credentials and networks (next section) and register the scheduled task ([Autostart](#autostart-windows-task-scheduler)).

## Configuration

### Credentials (`.env`)

Copy `.env.sample` to `.env` and fill in your Timebutler login:

```ini
TIMEBUTLER_USERNAME=your.email@example.com
TIMEBUTLER_PASSWORD=YourStrongPassword
```

On the first run the password is **moved into the Windows Credential Manager** (DPAPI-encrypted) and the `TIMEBUTLER_PASSWORD` line is removed from `.env` — afterwards `.env` only carries the username. Keeping the password in `.env` still works as a fallback, e.g. if the `keyring` package is not installed.

### Allowed Wi-Fi networks (`config/settings.json`)

Copy `config/settings.sample.json` to `config/settings.json` and list the networks that should trigger a punch-in:

```json
{
  "allowed_ssids": [
    "YourCompanyWiFi",
    "YourCompanyGuestWiFi"
  ]
}
```

The script only proceeds when the current SSID matches one of these entries. Save the file as **UTF-8** if your SSIDs contain umlauts.

## Usage

### Run manually

```bash
python timebutler_run.py
```

### Command line options

| Option | Effect |
|---|---|
| `--status` | Print a local status report (no browser): current Wi-Fi, punched in today?, scheduled task health, last log line |
| `--force-run` | Run even if already punched in today |
| `--headful` | Show the browser window (debugging) |
| `--debug` | Verbose logging |
| `--username` / `--password` | Override the stored credentials |

Example:

```bash
python timebutler_run.py --force-run --headful --debug
```

### Health check

```bash
python timebutler_run.py --status
```

```
Timebutler Auto - Status
----------------------------------------
WLAN: YourCompanyWiFi (erlaubt)
Heute gestempelt: ja
Task: Ready, letzter Lauf 06/02/2026 08:01:12 -> OK
Letzter Log-Eintrag: 2026-06-02 08:01:15 INFO Timebutler automation finished successfully.
```

## Autostart (Windows Task Scheduler)

> Already done if you used `install.ps1` — this section is for manual setup or fixing the triggers.

Register the task from an **elevated** PowerShell:

```powershell
.\setup_task.ps1 -PythonPath "C:\Path\To\pythonw.exe" -IncludeWlanTrigger
```

- `-PythonPath` — path to `pythonw.exe` (your venv's or the system one; defaults to `pythonw.exe` from `PATH`). Use `pythonw.exe`, not `python.exe`, so the script runs without a console window.
- `-IncludeWlanTrigger` — strongly recommended, see below.

### When does the task actually run?

By default the task only has a **logon trigger** — it fires when you *sign in* to Windows (after a reboot or sign-out). **Unlocking your laptop after sleep is not a logon**, so if you usually just close the lid, the task would rarely run.

`-IncludeWlanTrigger` adds an **event trigger on WLAN connections** (WLAN-AutoConfig events 8001/8002): the task also fires whenever Wi-Fi (re)connects — including waking from sleep in the office. The SSID filter and the once-per-day guard ensure this never double-punches.

<details>
<summary>Creating the task by hand in Task Scheduler (without <code>setup_task.ps1</code>)</summary>

1. Open **Task Scheduler** and create a new Basic Task.
2. **Trigger**: "When I log on" or "On an event".
3. **Action**: "Start a program".
4. **Program/script**: path to `pythonw.exe` (e.g. `C:\Python314\pythonw.exe`).
5. **Add arguments**: full path to `timebutler_run.py`.
6. **Start in**: the directory containing the script.

</details>

<details>
<summary>Why importing a task XML is not recommended</summary>

Prefer `setup_task.ps1` over importing an XML with `schtasks /create /xml`. If the XML's declared encoding does not match its actual file encoding, non-ASCII characters in paths (e.g. umlauts in your user name) get corrupted on import and the task fails on every run with error `0x8007010B` ("The directory name is invalid").

</details>

## n8n Mode (no PC required)

Instead of reacting to Wi-Fi on your laptop, n8n drives the full workday on a server:

| Step | When (defaults) |
|---|---|
| Punch in | random minute between **09:00 and 09:30** |
| Start break | random minute between **12:00 and 13:00** |
| End break | exactly **30 minutes** later |
| Punch out | **7.5–9 hours** after punching in (break included, so 7–8.5 h of net work) |

Weekends, public holidays (optional) and dates in `config/skip_dates.txt` are skipped.

**Architecture:** n8n cannot run a browser itself, so a small container (`tb_server.py`, Playwright + Chromium) exposes the clock as an HTTP API. The n8n workflow fetches the day's plan at 08:45 and uses *Wait* nodes to call the API at the planned times. Plans are persisted, so retries always see the same times, and every clock action is idempotent (starting a running clock is a no-op).

```
n8n (cron 08:45 Mon–Fri) ──GET /plan──▶ timebutler-clock ──Playwright──▶ Timebutler
      └─ Wait ▶ POST /clock/start ▶ Wait ▶ /pause ▶ Wait ▶ /resume ▶ Wait ▶ /stop
```

### 1. Start the clock server (next to n8n)

```bash
cp .env.server.sample .env.server   # fill in credentials and TB_API_TOKEN
cp config/skip_dates.sample.txt config/skip_dates.txt   # optional
N8N_NETWORK=n8n_default docker compose up -d --build
```

`N8N_NETWORK` must be the Docker network your n8n container is on (`docker network ls`). The server publishes no port; n8n reaches it at `http://timebutler-clock:8080`. For n8n Cloud, put the server behind an HTTPS reverse proxy instead and keep the token secret.

Generate the token with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

### 2. Import the n8n workflow

1. In n8n: **Credentials → New → Header Auth**, name `Timebutler Clock Token`, header name `Authorization`, value `Bearer <TB_API_TOKEN>`.
2. **Workflows → Import from file** → `n8n/timebutler_workflow.json`.
3. Select the credential in each HTTP node; adjust `base_url` in the *Konfiguration* node if needed.
4. Activate the workflow. Optionally set an *Error Workflow* (workflow settings) to get notified on failures.

### API

All endpoints except `/health` require `Authorization: Bearer <TB_API_TOKEN>`. Responses: `{"success": bool, "data": ..., "error": str|null}`.

| Endpoint | Purpose |
|---|---|
| `GET /health` | liveness probe |
| `GET /plan[?date=YYYY-MM-DD]` | the day's plan, or `{"work": false, "reason": ...}` |
| `GET /clock` | current state: `running`, `paused` or `stopped` |
| `POST /clock/start` · `/pause` · `/resume` · `/stop` | clock actions (idempotent) |

### Settings (`.env.server`)

| Variable | Default | Meaning |
|---|---|---|
| `TB_START_WINDOW` | `09:00-09:30` | punch-in window |
| `TB_SHIFT_HOURS` | `7.5-9` | punch-in → punch-out, break included |
| `TB_BREAK_MINUTES` | `30` | break length |
| `TB_BREAK_WINDOW` | `12:00-13:00` | break start window |
| `TB_WORKDAYS` | `1,2,3,4,5` | ISO weekdays (Mon = 1) |
| `TB_HOLIDAY_REGION` | – | skip public holidays, e.g. `DE-BY`, `DE-NW` |
| `TB_TIMEZONE` | `Europe/Berlin` | timezone of the plan |

Invalid combinations are rejected at startup — for example a break that could start more than 6 hours after punching in (German working-time law).

`config/skip_dates.txt` takes one date (`2026-12-24`) or range (`2026-10-05..2026-10-09`) per line and is re-read on every plan request — add vacation or sick days there. Adding *today* after the workflow started is fine too: `/clock/start` checks the plan again and refuses to punch in.

## Troubleshooting

Start with the health check — it shows the task's last result code and the last log line:

```bash
python timebutler_run.py --status
```

| Symptom | Cause & fix |
|---|---|
| Task never seems to run | Check `Get-ScheduledTaskInfo -TaskName "TimebutlerAuto"`. `LastTaskResult 2147942667` (`0x8007010B`, "directory name is invalid") means the registered path is broken — typically from importing a task XML with a mismatched encoding declaration. Re-register with `.\setup_task.ps1`. |
| Task fires at sign-in but never after sleep | The WLAN trigger is missing — re-register with `-IncludeWlanTrigger` (see [Autostart](#autostart-windows-task-scheduler)). |
| "Could not locate the Kommen/Start button" | Timebutler occasionally redesigns its UI and the selectors change (most recently UI 3.0 in June 2026). Update this repo (`git pull`); if it still fails, run with `--headful --debug` and check the error screenshot in `state/`. |
| SSID with umlauts never matches | Save `config/settings.json` as UTF-8. The script decodes `netsh` output with the OEM codepage, so umlauts in Wi-Fi names are supported. |
| "Netsh command not found" | The script uses `netsh` to detect the SSID — it only runs on Windows. |
| Login fails at a cookie banner | The script handles most consent banners (consentmanager.net and similar). Run with `--headful --debug` to see what's happening — the site may have introduced a new banner type. |

Where to look:

- **Logs**: `logs/timebutler.log`
- **Error screenshots & HTML dumps**: `state/` (written automatically on failure; artifacts older than 30 days are cleaned up on each run)

## Features

- **Automated login** with stored credentials, including cookie consent handling.
- **SSID filtering** — only runs on your configured Wi-Fi networks.
- **Once per day** — never double-punches (override with `--force-run`).
- **Timebutler UI 3.0 support** — works with the redesigned topbar time recorder (June 2026); the legacy UI remains supported as a fallback.
- **Secure credential storage** — password lives DPAPI-encrypted in the Windows Credential Manager; an existing `.env` password is migrated automatically.
- **Windows notifications** on failure (and success).
- **Headless by default**, with session persistence to avoid repeated logins.
- **Error forensics** — screenshots and HTML dumps on failure.
- **n8n mode** — full-day automation (in, break, out) from a server, see [n8n Mode](#n8n-mode-no-pc-required).

## Development

Run the test suite with:

```bash
python -m pytest
```

The tests mock all network and browser interaction, so they run without Playwright browsers or a Timebutler account. CI runs them on Ubuntu and Windows (Python 3.9 and 3.12) for every push and pull request.

Note: the selector definitions live in `tb_selectors.py` — the module is deliberately *not* named `selectors.py`, since that would shadow Python's standard library module of the same name.

## License

[MIT License](LICENSE)

## Disclaimer

This tool is not affiliated with Timebutler. Use it at your own risk.
