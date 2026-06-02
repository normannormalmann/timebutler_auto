# Timebutler Auto-Punch

[![CI](https://github.com/normannormalmann/timebutler_auto/actions/workflows/ci.yml/badge.svg)](https://github.com/normannormalmann/timebutler_auto/actions/workflows/ci.yml)

Automated time tracking script for [Timebutler](https://app.timebutler.com/). This tool automatically logs you in and "punches in" (starts time recording) when you are connected to specific Wi-Fi networks (e.g., your office Wi-Fi).

## Features

- **Automated Login**: Handles login using credentials stored in environment variables.
- **Cookie Consent Handler**: Automatically detects and closes cookie consent banners (e.g., consentmanager.net).
- **SSID Filtering**: Only runs when connected to specified Wi-Fi networks (configurable via `config/settings.json`).
- **Run Once Per Day**: Prevents multiple punch-ins on the same day unless forced.
- **Headless Mode**: Runs silently in the background by default.
- **Error Handling**: Captures screenshots and HTML dumps if an error occurs.
- **Failure Notifications**: Shows a Windows notification when a punch-in attempt fails (and on success).
- **Credential Manager**: The password is stored DPAPI-encrypted in the Windows Credential Manager; an existing `.env` password is migrated automatically on the first run.
- **State Persistence**: Saves login session to avoid repeated logins.

## Prerequisites

- Python 3.8 or higher
- Chrome/Chromium browser (installed via Playwright)

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/normannormalmann/timebutler_auto.git
    cd timebutler_auto
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv .venv
    # Windows
    .venv\Scripts\activate
    # Linux/Mac
    source .venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    playwright install chromium
    ```

## Configuration

### 1. Credentials
Create a `.env` file in the root directory (based on `.env.sample`) and add your Timebutler credentials:

```ini
TIMEBUTLER_USERNAME=your.email@example.com
TIMEBUTLER_PASSWORD=YourStrongPassword
```

On the first run, the password is moved into the Windows Credential Manager (DPAPI-encrypted) and the `TIMEBUTLER_PASSWORD` line is removed from `.env`. After migration, `.env` only carries `TIMEBUTLER_USERNAME`. Keeping `TIMEBUTLER_PASSWORD` in `.env` still works as a fallback — for example if the `keyring` package is not installed.

### 2. Allowed Wi-Fi Networks
Create a `config/settings.json` file (based on `config/settings.sample.json`) to define which Wi-Fi networks should trigger the automation:

```json
{
  "allowed_ssids": [
    "YourCompanyWiFi",
    "YourCompanyGuestWiFi"
  ]
}
```

The script will check your current Wi-Fi SSID and only proceed if it matches one of the entries in this list.

## Usage

### Manual Run
Run the script manually from your terminal:

```bash
python timebutler_run.py
```

### Command Line Arguments
- `--force-run`: Run the script even if it has already successfully run today.
- `--headful`: Run with the browser window visible (useful for debugging).
- `--debug`: Enable verbose logging.
- `--username`: Override the username from `.env`.
- `--password`: Override the password from `.env`.
- `--status`: Print a local status report (current Wi-Fi, whether you punched in today, scheduled task health, last log line) without opening a browser.

Example:
```bash
python timebutler_run.py --force-run --headful
```

### Checking the Setup

```bash
python timebutler_run.py --status
```

Example output:
```
Timebutler Auto - Status
----------------------------------------
WLAN: YourCompanyWiFi (erlaubt)
Heute gestempelt: ja
Task: Ready, letzter Lauf 06/02/2026 08:01:12 -> OK
Letzter Log-Eintrag: 2026-06-02 08:01:15 INFO Timebutler automation finished successfully.
```

### Automation (Windows Task Scheduler)

#### Method 1: Using the Interactive Installer (Recommended)

The easiest way to set up everything is using the interactive installer script, which supports both **English** and **German**.

1.  Open **PowerShell** as Administrator.
2.  Navigate to the project directory:
    ```powershell
    cd "C:\Path\To\timebutler_auto"
    ```
3.  Run the installer:
    ```powershell
    .\install.ps1
    ```

The installer guides you through:
- **Language Selection**: Choose between English and German.
- **Credentials Setup**: Enter your Timebutler email and password securely.
- **Network Configuration**: Automatically detects your current Wi-Fi and allows you to select allowed networks from your saved profiles.
- **Environment Setup**: Automatically checks for Python (and offers to install it via Winget if missing), creates a virtual environment, and installs necessary dependencies (including Playwright browsers).
- **Task Registration**: Registers the scheduled task to run automatically on login.

#### Method 2: Manual Setup

If you prefer to configure everything manually:

1.  **Configure Credentials**: Copy `.env.sample` to `.env` and fill in your details.
2.  **Configure Networks**: Copy `config/settings.sample.json` to `config/settings.json` and add your SSIDs (save as UTF-8 if they contain umlauts).
3.  **Register Task**: Run the underlying setup script (requires an elevated PowerShell):
    ```powershell
    .\setup_task.ps1 -PythonPath "C:\Path\To\pythonw.exe" -IncludeWlanTrigger
    ```
    - `-PythonPath`: Path to `pythonw.exe` (your venv's or the system one). Defaults to `pythonw.exe` from `PATH`.
    - `-IncludeWlanTrigger`: Strongly recommended, see below.

#### When does the task actually run? (Triggers)

By default the task only has a **logon trigger** — it fires when you *sign in* to Windows (after a reboot or sign-out). **Unlocking your laptop after sleep is not a logon**, so if you usually just close the lid, the task would rarely run.

The `-IncludeWlanTrigger` switch adds an **event trigger on WLAN connections** (WLAN-AutoConfig events 8001/8002): the task also fires whenever Wi-Fi (re)connects — including waking from sleep in the office. The script's SSID filter and once-per-day guard make sure this never double-punches.

#### Importing a task XML (not recommended)

Prefer `setup_task.ps1` over importing an XML with `schtasks /create /xml`. If the XML's declared encoding does not match its actual file encoding, non-ASCII characters in paths (e.g. umlauts in your user name) get corrupted on import and the task fails on every run with error `0x8007010B` ("The directory name is invalid").

Alternatively, create the task manually in Task Scheduler:

1.  Open **Task Scheduler**.
2.  Create a new Basic Task.
3.  **Trigger**: "When I log on" or "On an event".
4.  **Action**: "Start a program".
5.  **Program/script**: Path to your python executable (e.g., `C:\Python314\pythonw.exe`).
6.  **Add arguments**: Full path to `timebutler_run.py` (e.g., `C:\Path\To\timebutler_auto\timebutler_run.py`).
7.  **Start in**: The directory containing the script (e.g., `C:\Path\To\timebutler_auto`).

**Important:** Use `pythonw.exe` instead of `python.exe` to run the script silently in the background.

## Troubleshooting

- **Quick health check**: Run `python timebutler_run.py --status` first — it shows the scheduled task's last result code and the last log line.
- **Logs**: Check `logs/timebutler.log` for execution details.
- **Screenshots**: If the script fails, error screenshots and HTML dumps are saved in the `state/` directory.
- **Task never seems to run**: Check `Get-ScheduledTaskInfo -TaskName "TimebutlerAuto"`:
  - `LastTaskResult 2147942667` (`0x8007010B`, "directory name is invalid"): the registered path is broken — typically caused by importing a task XML with a mismatched encoding declaration (umlauts in the path get corrupted). Re-register with `.\setup_task.ps1`.
  - Task only fires at sign-in, never after sleep: you are missing the WLAN trigger — re-register with `-IncludeWlanTrigger` (see above).
- **SSID with umlauts never matches**: Make sure `config/settings.json` is saved as UTF-8. The script decodes `netsh` output with the OEM codepage, so umlauts in Wi-Fi names are supported.
- **"Netsh command not found"**: Ensure you are running on Windows, as the script uses `netsh` to detect the SSID.
- **Cookie Banner Issues**: The script automatically handles most cookie consent banners. If login fails:
  - Run with `--headful --debug` to see what's happening
  - Check if a new banner type has been implemented by the website
  - The script supports multiple banner types (consentmanager.net and similar)

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