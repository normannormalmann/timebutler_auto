from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from datetime import date, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Set

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
        load_dotenv = None  # type: ignore

import selectors as sel  # local module
from selectors import TimeoutError

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


BASE_DIR = Path(__file__).resolve().parent
STATE_DIR = BASE_DIR / "state"
LOG_DIR = BASE_DIR / "logs"
CONFIG_DIR = BASE_DIR / "config"
LAST_RUN_FILE = STATE_DIR / "last_run.txt"
STORAGE_STATE_FILE = STATE_DIR / "storage_state.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
LOG_FILE = LOG_DIR / "timebutler.log"
TIMEBUTLER_URL = "https://app.timebutler.com/"


class RunContext:
    def __init__(self, args: argparse.Namespace, logger: logging.Logger):
        self.args = args
        self.logger = logger
        self.now = datetime.now()
        self.screenshot_prefix = self.now.strftime("%Y%m%d_%H%M%S")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automate the Timebutler punch-in workflow.")
    parser.add_argument(
        "--force-run",
        action="store_true",
        help="Run even if today's stamp already exists.",
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Launch Chromium with a visible window (for debugging).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose debug logging.",
    )
    parser.add_argument(
        "--username",
        help="Override username (otherwise read from TIMEBUTLER_USERNAME env).",
    )
    parser.add_argument(
        "--password",
        help="Override password (otherwise read from TIMEBUTLER_PASSWORD env).",
    )
    return parser.parse_args()


def ensure_directories() -> None:
    for path in (STATE_DIR, LOG_DIR, CONFIG_DIR):
        path.mkdir(parents=True, exist_ok=True)


def load_allowed_ssids(logger: logging.Logger) -> Set[str]:
    if not SETTINGS_FILE.exists():
        logger.error("Settings file not found: %s", SETTINGS_FILE)
        return set()
    
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        ssids = set(data.get("allowed_ssids", []))
        if not ssids:
            logger.warning("No 'allowed_ssids' found in settings file.")
        return ssids
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse settings file: %s", exc)
        return set()
    except Exception as exc:
        logger.error("Error reading settings file: %s", exc)
        return set()


def init_logging(debug: bool) -> logging.Logger:
    logger = logging.getLogger("timebutler")
    logger.setLevel(logging.DEBUG if debug else logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=5)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.addHandler(console)

    return logger


def load_credentials(args: argparse.Namespace, logger: logging.Logger) -> tuple[str, str]:
    if load_dotenv is not None:
        load_dotenv(BASE_DIR / ".." / ".env")
        load_dotenv(BASE_DIR / ".env")

    username = args.username or os.getenv("TIMEBUTLER_USERNAME")
    password = args.password or os.getenv("TIMEBUTLER_PASSWORD")

    if not username or not password:
        logger.error(
            "Missing credentials. Provide TIMEBUTLER_USERNAME and TIMEBUTLER_PASSWORD environment variables."
        )
        sys.exit(2)
    return username, password


def get_current_ssid(logger: logging.Logger) -> Optional[str]:
    try:
        proc = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
        )
    except FileNotFoundError:
        logger.error("netsh command not found. Cannot determine SSID.")
        return None

    if proc.returncode != 0:
        logger.error("netsh failed with code %s: %s", proc.returncode, proc.stderr.strip())
        return None

    pattern = re.compile(r"^\s*SSID\s*:\s*(.+)$", re.MULTILINE)
    match = pattern.search(proc.stdout)
    if match:
        ssid = match.group(1).strip()
        # ignore blank values and VirtualBox pseudo entries
        if ssid and ssid.lower() != "ssid":
            return ssid
    logger.warning("Could not detect SSID from netsh output.")
    return None


def already_ran_today(force: bool, logger: logging.Logger) -> bool:
    if force:
        return False
    if LAST_RUN_FILE.exists():
        try:
            stored = LAST_RUN_FILE.read_text(encoding="utf-8").strip()
            if stored and stored == date.today().isoformat():
                logger.info("Timebutler automation already completed today (%s).", stored)
                return True
        except OSError as exc:
            logger.warning("Failed to read last_run flag: %s", exc)
    return False


def write_last_run(logger: logging.Logger) -> None:
    try:
        LAST_RUN_FILE.write_text(date.today().isoformat(), encoding="utf-8")
        logger.info("Recorded successful run for %s.", date.today().isoformat())
    except OSError as exc:
        logger.error("Failed to write last_run flag: %s", exc)


def is_logged_in(page) -> bool:
    url = page.url

    # Check if we're on a login page
    if "login" in url.lower():
        return False

    # If we're on the main dashboard /do page, we're logged in
    if "/do" in url and "login" not in url.lower():
        return True

    # Check for logged-in indicators
    if sel.is_any_visible(page, sel.USER_AVATAR):
        return True
    if sel.is_any_visible(page, sel.START_BUTTON):
        return True

    return False


def perform_login(page, username: str, password: str, logger: logging.Logger) -> None:
    logger.info("Performing login via form.")
    sel.fill_first(page, sel.LOGIN_USER, username)
    sel.fill_first(page, sel.LOGIN_PASS, "")
    sel.fill_first(page, sel.LOGIN_PASS, password)

    # Close cookie consent banner before clicking submit
    sel.close_cookie_banner(page, logger)

    sel.click_first(page, sel.LOGIN_SUBMIT)

    # Wait for page to navigate and load after login
    logger.info("Waiting for login to complete...")
    page.wait_for_load_state("networkidle", timeout=10_000)
    page.wait_for_timeout(3_000)

    if not is_logged_in(page):
        logger.error(f"Login check failed. Current URL: {page.url}")
        raise RuntimeError("Login did not finish successfully.")


def ensure_on_dashboard(page, logger: logging.Logger) -> None:
    logger.debug("Ensuring dashboard is visible.")
    if page.url.startswith(TIMEBUTLER_URL):
        return
    page.goto(TIMEBUTLER_URL, wait_until="networkidle", timeout=30_000)


def click_start_button(page, logger: logging.Logger) -> None:
    if sel.is_any_visible(page, sel.RUNNING_INDICATORS):
        logger.info("Zeiterfassung läuft bereits laut UI.")
        return

    # Try to find start button directly (if already visible)
    if not sel.is_any_visible(page, sel.START_BUTTON):
        logger.info("Start button not visible. Attempting to open Stempeluhr menu.")
        try:
            sel.click_first(page, sel.STEMPEL_NAV_LINKS, timeout=5_000)
        except sel.TimeoutError:
            logger.warning("Could not find Stempeluhr menu toggle.")

    try:
        sel.click_first(page, sel.START_BUTTON, timeout=10_000)
    except sel.TimeoutError as exc:
        logger.error(f"Could not find the START_BUTTON. Current URL: {page.url}")
        raise RuntimeError("Could not locate the Kommen/Start button.") from exc

    logger.info("Clicked the Kommen/Start button, waiting for confirmation.")

    for selector in sel.RUNNING_INDICATORS:
        locator = page.locator(selector)
        try:
            locator.wait_for(state="visible", timeout=10_000)
            logger.info("Detected running indicator via '%s'.", selector)
            return
        except sel.TimeoutError:
            continue
    raise RuntimeError("Start confirmation did not appear.")


def capture_debug_artifacts(page, ctx: RunContext) -> None:
    timestamp = ctx.screenshot_prefix
    png_path = STATE_DIR / f"error_{timestamp}.png"
    html_path = STATE_DIR / f"error_{timestamp}.html"
    try:
        page.screenshot(path=str(png_path), full_page=True)
        ctx.logger.error("Saved error screenshot to %s", png_path)
    except Exception as exc:  # pragma: no cover - best-effort
        ctx.logger.error("Failed to save screenshot: %s", exc)
    try:
        html_path.write_text(page.content(), encoding="utf-8")
        ctx.logger.error("Saved error HTML dump to %s", html_path)
    except Exception as exc:  # pragma: no cover
        ctx.logger.error("Failed to save HTML dump: %s", exc)


def run_playwright(ctx: RunContext, username: str, password: str) -> None:
    if sync_playwright is None:  # pragma: no cover
        raise RuntimeError(
            "Playwright is not installed. Run 'pip install -r requirements.txt' and 'playwright install chromium'."
        )
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not ctx.args.headful)
        context_kwargs = {}
        if STORAGE_STATE_FILE.exists():
            context_kwargs["storage_state"] = str(STORAGE_STATE_FILE)
        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        page.set_default_navigation_timeout(30_000)
        page.set_default_timeout(12_000)

        try:
            ctx.logger.info("Opening %s", TIMEBUTLER_URL)
            page.goto(TIMEBUTLER_URL, wait_until="networkidle", timeout=30_000)

            if not is_logged_in(page):
                perform_login(page, username, password, ctx.logger)
            else:
                ctx.logger.info("Session already authenticated.")

            ensure_on_dashboard(page, ctx.logger)
            click_start_button(page, ctx.logger)
            context.storage_state(path=str(STORAGE_STATE_FILE))
            ctx.logger.info("Persisted Playwright storage state to %s", STORAGE_STATE_FILE)
        except Exception:
            capture_debug_artifacts(page, ctx)
            raise
        finally:
            context.close()
            browser.close()


def show_notification(title: str, message: str) -> None:
    """Displays a Windows notification using PowerShell."""
    ps_script = f"""
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $icon = New-Object System.Windows.Forms.NotifyIcon
    $icon.Icon = [System.Drawing.SystemIcons]::Information
    $icon.BalloonTipTitle = '{title}'
    $icon.BalloonTipText = '{message}'
    $icon.Visible = $true
    $icon.ShowBalloonTip(3000)
    Start-Sleep -Seconds 3
    $icon.Dispose()
    """
    try:
        subprocess.run(["powershell", "-Command", ps_script], check=False, creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:
        # Fallback for systems where CREATE_NO_WINDOW might not be available or other errors
        subprocess.run(["powershell", "-Command", ps_script], check=False)


def main() -> int:
    args = parse_args()
    ensure_directories()
    logger = init_logging(debug=args.debug)
    username, password = load_credentials(args, logger)
    allowed_ssids = load_allowed_ssids(logger)

    ctx = RunContext(args, logger)

    ssid = get_current_ssid(logger)
    if ssid is None:
        logger.info("Unable to determine SSID. Skipping run.")
        return 0

    normalized_ssid = ssid.strip()
    if normalized_ssid not in allowed_ssids and normalized_ssid.lower() not in {
        x.lower() for x in allowed_ssids
    }:
        logger.info("Current SSID '%s' not in the allowed list. Exiting.", normalized_ssid)
        return 0

    if already_ran_today(args.force_run, logger):
        return 0

    try:
        run_playwright(ctx, username, password)
    except Exception as exc:
        logger.exception("Automation failed: %s", exc)
        return 1

    write_last_run(logger)
    logger.info("Timebutler automation finished successfully.")
    
    # Show success notification
    show_notification("Timebutler Auto", "Erfolgreich eingestempelt!")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
