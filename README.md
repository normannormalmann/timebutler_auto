# Timebutler Auto-Punch

Automated time tracking script for [Timebutler](https://app.timebutler.com/). This tool automatically logs you in and "punches in" (starts time recording) when you are connected to specific Wi-Fi networks (e.g., your office Wi-Fi).

## Features

- **Automated Login**: Handles login using credentials stored in environment variables.
- **Cookie Consent Handler**: Automatically detects and closes cookie consent banners (e.g., consentmanager.net).
- **SSID Filtering**: Only runs when connected to specified Wi-Fi networks (configurable via `config/settings.json`).
- **Run Once Per Day**: Prevents multiple punch-ins on the same day unless forced.
- **Headless Mode**: Runs silently in the background by default.
- **Error Handling**: Captures screenshots and HTML dumps if an error occurs.
- **State Persistence**: Saves login session to avoid repeated logins.

## Prerequisites

- Python 3.8 or higher
- Chrome/Chromium browser (installed via Playwright)

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/yourusername/timebutler-auto.git
    cd timebutler-auto
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

Example:
```bash
python timebutler_run.py --force-run --headful
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
2.  **Configure Networks**: Copy `config/settings.sample.json` to `config/settings.json` and add your SSIDs.
3.  **Register Task**: Run the underlying setup script:
    ```powershell
    .\setup_task.ps1
    ```

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

- **Logs**: Check `logs/timebutler.log` for execution details.
- **Screenshots**: If the script fails, error screenshots and HTML dumps are saved in the `state/` directory.
- **"Netsh command not found"**: Ensure you are running on Windows, as the script uses `netsh` to detect the SSID.
- **Cookie Banner Issues**: The script automatically handles most cookie consent banners. If login fails:
  - Run with `--headful --debug` to see what's happening
  - Check if a new banner type has been implemented by the website
  - The script supports multiple banner types (consentmanager.net and similar)

## License

[MIT License](LICENSE)

## Disclaimer

This tool is not affiliated with Timebutler. Use it at your own risk.