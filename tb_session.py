"""
Authenticated Playwright session for Timebutler, shared by the Windows
punch-in script (timebutler_run.py) and the n8n clock server (tb_server.py).
"""
from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

import tb_selectors as sel

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

TIMEBUTLER_URL = "https://app.timebutler.com/"


def is_logged_in(page) -> bool:
    url = page.url

    # Check if we're on a login page
    if "login" in url.lower():
        return False

    # If we're on the main dashboard /do page, we're logged in
    # (match /do as a path segment, not substrings like /download)
    if re.search(r"/do(?:[/?#]|$)", url):
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
        logger.error("Login check failed. Current URL: %s", page.url)
        raise RuntimeError("Login did not finish successfully.")


def ensure_on_dashboard(page, logger: logging.Logger) -> None:
    logger.debug("Ensuring dashboard is visible.")
    if page.url.startswith(TIMEBUTLER_URL):
        return
    page.goto(TIMEBUTLER_URL, wait_until="networkidle", timeout=30_000)


def capture_debug_artifacts(page, artifact_dir: Path, logger: logging.Logger) -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    png_path = artifact_dir / f"error_{timestamp}.png"
    html_path = artifact_dir / f"error_{timestamp}.html"
    try:
        page.screenshot(path=str(png_path), full_page=True)
        logger.error("Saved error screenshot to %s", png_path)
    except Exception as exc:  # pragma: no cover - best-effort
        logger.error("Failed to save screenshot: %s", exc)
    try:
        html_path.write_text(page.content(), encoding="utf-8")
        logger.error("Saved error HTML dump to %s", html_path)
    except Exception as exc:  # pragma: no cover
        logger.error("Failed to save HTML dump: %s", exc)


@contextmanager
def dashboard_page(
    username: str,
    password: str,
    storage_state_file: Path,
    logger: logging.Logger,
    headless: bool = True,
) -> Iterator:
    """Yields a logged-in Timebutler dashboard page.

    The session cookies are persisted to `storage_state_file` on success so the
    next run can skip the login form. On any error a screenshot and HTML dump
    are written next to the storage state file before the error propagates.
    """
    if sync_playwright is None:  # pragma: no cover
        raise RuntimeError(
            "Playwright is not installed. Run 'pip install -r requirements.txt' and 'playwright install chromium'."
        )
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context_kwargs = {}
        if storage_state_file.exists():
            context_kwargs["storage_state"] = str(storage_state_file)
        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        page.set_default_navigation_timeout(30_000)
        page.set_default_timeout(12_000)

        try:
            logger.info("Opening %s", TIMEBUTLER_URL)
            page.goto(TIMEBUTLER_URL, wait_until="networkidle", timeout=30_000)

            if not is_logged_in(page):
                perform_login(page, username, password, logger)
            else:
                logger.info("Session already authenticated.")

            ensure_on_dashboard(page, logger)
            yield page
            context.storage_state(path=str(storage_state_file))
            logger.info("Persisted Playwright storage state to %s", storage_state_file)
        except Exception:
            capture_debug_artifacts(page, storage_state_file.parent, logger)
            raise
        finally:
            context.close()
            browser.close()
