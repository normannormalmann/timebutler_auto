"""
Selector definitions and helper utilities for the Timebutler automation.
The selectors are intentionally redundant so we can gracefully fall back
if the UI changes slightly (text, role, css classes, etc.).
"""
from __future__ import annotations

from typing import Iterable, Sequence, Any

try:
    from playwright.sync_api import Locator, Page, TimeoutError
except ImportError:  # pragma: no cover
    class TimeoutError(Exception):
        """Fallback TimeoutError when Playwright is not installed."""

    Locator = Page = Any  # type: ignore


# Login form selectors
LOGIN_USER: Sequence[str] = (
    "#login",
    "input[name='login']",
    "input[type='email']",
    "input[autocomplete='username']",
)

LOGIN_PASS: Sequence[str] = (
    "#passwort",
    "input[name='passwort']",
    "input[type='password']",
    "input[autocomplete='current-password']",
)

LOGIN_SUBMIT: Sequence[str] = (
    "form#loginform button[type='submit']",
    "form#loginform button.btn.btn-primary",
    "button:has-text('Anmelden')",
    "role=button[name='Anmelden']",
    "text=/Anmelden|Login/i",
)

# Cookie consent banner
COOKIE_BANNER: Sequence[str] = (
    "#cmpbox",
    ".cmpbox",
    "#cmpwrapper",
    ".cmpwrapper",
    "div[id*='cookie']",
    "div[class*='cookie']",
    "div[id*='consent']",
    "div[class*='consent']",
)

COOKIE_ACCEPT: Sequence[str] = (
    "#cmpwelcomebtnyes",
    "a:has-text('Alle akzeptieren')",
    "a:has-text('Alles akzeptieren')",
    "button:has-text('Alle akzeptieren')",
    "button:has-text('Alles akzeptieren')",
    "a:has-text('Akzeptieren')",
    "button:has-text('Akzeptieren')",
    "button:has-text('Accept All')",
    "button[id*='accept']",
    "button[class*='accept']",
    "#cmpbntyes",
    ".cmpbtnyes",
)


# Dashboard / stamping controls
STEMPEL_NAV_LINKS: Sequence[str] = (
    "#timeRecShowBtn",
    "a[href*='time-rec']",
    "nav >> text=/Stempeluhr/i",
    "button:has-text('Stempeluhr')",
    "role=link[name=/Stempeluhr|Zeiterfassung/i]",
)

START_BUTTON: Sequence[str] = (
    "#recBtnStart",
    "a:has-text('Starten')",
    "a:has-text('Kommen')",
    "button:has-text('Kommen')",
    "button:has-text('Start')",
    "button:has-text('Arbeitsbeginn')",
    "button[data-action*='start']",
    "role=button[name=/Kommen|Start|Arbeitsbeginn/i]",
    "[data-testid='startTimeRecordingButton']",
)

RUNNING_INDICATORS: Sequence[str] = (
    "#recDD[data-running='1']",
    ".dropdown-toggle.running",
    "[data-status*='running']",
    ".recTimeIndicator.running",
    "#rectime.running",
    "text=/läuft|gestartet|läuft seit/i",
)

USER_AVATAR: Sequence[str] = (
    ".user-id-truncated",
    "nav [data-testid='userMenu']",
    ".user-initials",
    ".avatar-initials",
)


def _find_first_visible(
    page: Page,
    selectors: Iterable[str],
    timeout: float = 10_000,
) -> Locator:
    last_error: TimeoutError | None = None
    for selector in selectors:
        locator = page.locator(selector)
        try:
            locator.wait_for(state="visible", timeout=timeout)
            return locator
        except TimeoutError as exc:
            last_error = exc
    raise TimeoutError(f"Could not find any selector from: {selectors}") from last_error


def fill_first(
    page: Page,
    selectors: Iterable[str],
    value: str,
    timeout: float = 10_000,
) -> None:
    locator = _find_first_visible(page, selectors, timeout)
    locator.fill(value)


def click_first(
    page: Page,
    selectors: Iterable[str],
    timeout: float = 10_000,
) -> None:
    locator = _find_first_visible(page, selectors, timeout)
    locator.click()


def is_any_visible(page: Page, selectors: Iterable[str]) -> bool:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            locator.wait_for(state="visible", timeout=1_000)
            return True
        except TimeoutError:
            continue
    return False


def close_cookie_banner(page: Page, logger=None) -> bool:
    """
    Attempts to close cookie consent banners.

    Returns:
        True if banner was found and closed, False otherwise.
    """
    try:
        if logger:
            logger.debug("Checking for cookie banner...")

        # Wait a bit for banner to appear (it might be lazy-loaded)
        page.wait_for_timeout(500)

        # Try to find banner with longer timeout
        banner_found = False
        for selector in COOKIE_BANNER:
            locator = page.locator(selector).first
            try:
                locator.wait_for(state="visible", timeout=3_000)
                banner_found = True
                if logger:
                    logger.info(f"Cookie consent banner detected: {selector}")
                break
            except Exception:
                continue

        if not banner_found:
            if logger:
                logger.debug("No cookie banner detected.")
            return False

        if logger:
            logger.info("Attempting to close cookie banner...")

        # Strategy 1: Try to find and click accept button
        for selector in COOKIE_ACCEPT:
            locator = page.locator(selector).first
            try:
                locator.wait_for(state="visible", timeout=2_000)

                # Try clicking with force to bypass overlay issues
                locator.click(force=True, timeout=5_000)

                if logger:
                    logger.info(f"Successfully clicked accept button: {selector}")

                # Wait a moment for the banner to disappear
                page.wait_for_timeout(1000)

                # Verify banner is gone
                if not is_any_visible(page, COOKIE_BANNER):
                    if logger:
                        logger.info("Cookie banner closed successfully.")
                    return True

            except Exception:
                continue

        # Strategy 2: No accept button found - remove banner with JavaScript
        if logger:
            logger.warning("Could not find accept button. Removing banner with JavaScript...")

        try:
            result = page.evaluate("""
                () => {
                    const banner = document.querySelector('#cmpbox') ||
                                   document.querySelector('.cmpbox') ||
                                   document.querySelector('#cmpwrapper') ||
                                   document.querySelector('.cmpwrapper');
                    if (banner) {
                        banner.style.display = 'none';
                        banner.style.visibility = 'hidden';
                        banner.style.pointerEvents = 'none';
                        banner.remove();
                        return 'Banner removed';
                    }
                    return 'No banner found';
                }
            """)

            if logger:
                logger.info(f"JavaScript result: {result}")

            # Wait a moment for DOM to update
            page.wait_for_timeout(500)

            return True

        except Exception as exc:
            if logger:
                logger.warning(f"Failed to remove banner with JavaScript: {exc}")

        return False

    except Exception as exc:
        if logger:
            logger.warning(f"Error while closing cookie banner: {exc}")
        return False
