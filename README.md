# Timebutler Auto-Punch

[![CI](https://github.com/normannormalmann/timebutler_auto/actions/workflows/ci.yml/badge.svg)](https://github.com/normannormalmann/timebutler_auto/actions/workflows/ci.yml)

Automated time tracking for [Timebutler](https://app.timebutler.com/): the tool logs in and "punches in" (starts time recording) automatically whenever you are connected to specific Wi-Fi networks — e.g. your office Wi-Fi. It runs silently in the background, at most once per day.

**How it works:** a Windows scheduled task starts the script at sign-in and on every Wi-Fi (re)connect. The script checks your current SSID against an allowlist, and if it matches — and you haven't punched in today — it opens a headless browser, logs in and starts the time recorder.

## Contents

- [Quick Start](#quick-start)
- [Manual Installation](#manual-installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Autostart (Windows Task Scheduler)](#autostart-windows-task-scheduler)
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
- **Task registration** — registers the scheduled task so the script runs automatically.

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
- **Error screenshots & HTML dumps**: `state/` (written automatically on failure)

## Features

- **Automated login** with stored credentials, including cookie consent handling.
- **SSID filtering** — only runs on your configured Wi-Fi networks.
- **Once per day** — never double-punches (override with `--force-run`).
- **Timebutler UI 3.0 support** — works with the redesigned topbar time recorder (June 2026); the legacy UI remains supported as a fallback.
- **Secure credential storage** — password lives DPAPI-encrypted in the Windows Credential Manager; an existing `.env` password is migrated automatically.
- **Windows notifications** on failure (and success).
- **Headless by default**, with session persistence to avoid repeated logins.
- **Error forensics** — screenshots and HTML dumps on failure.

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
