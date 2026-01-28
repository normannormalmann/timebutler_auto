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
