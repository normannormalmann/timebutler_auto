"""
Time recorder actions for the Timebutler UI 3.x topbar clock.

The clock element exposes its state as data attributes, e.g.
<div id="time-clock" data-running="1" data-paused="0" ...>, which is far more
reliable than looking at button visibility. Every action is idempotent:
starting a running clock or stopping a stopped one is a no-op, so n8n can
safely retry a request.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Dict, List

CLOCK = "#time-clock"
PLAY_BUTTON = "#time-clock-play"
PAUSE_BUTTON = "#time-clock-pause-btn"
RESUME_BUTTON = "#time-clock-resume-btn"
STOP_BUTTON = "#time-clock-stop"
STOP_CONFIRM = "#time-clock-stop-confirm"
SAVE_ERROR_PANEL = "#time-clock-save-error"
SAVE_ERROR_MESSAGE = "#time-clock-save-error-msg"

ACTIONS = ("start", "pause", "resume", "stop")
CONFIRM_TIMEOUT_MS = 15_000


@dataclass(frozen=True)
class ClockState:
    running: bool
    paused: bool

    @property
    def name(self) -> str:
        if self.paused:
            return "paused"
        return "running" if self.running else "stopped"


# Button clicks needed to get from a state to the goal of an action.
_STEPS: Dict[str, Dict[str, List[str]]] = {
    "start": {"stopped": ["play"], "paused": ["resume"], "running": []},
    "pause": {"stopped": [], "paused": [], "running": ["pause"]},
    "resume": {"stopped": [], "paused": ["resume"], "running": []},
    # Timebutler saves a paused entry as well, but resuming first keeps the
    # recorded break exactly as long as planned.
    "stop": {"stopped": [], "paused": ["resume", "stop"], "running": ["stop"]},
}

# State expected after each click, used to confirm that it took effect.
_EXPECTED_AFTER: Dict[str, str] = {
    "play": "running",
    "resume": "running",
    "pause": "paused",
    "stop": "stopped",
}

_STATE_SELECTORS: Dict[str, str] = {
    "running": f"{CLOCK}[data-running='1'][data-paused='0']",
    "paused": f"{CLOCK}[data-paused='1']",
    "stopped": f"{CLOCK}[data-running='0'][data-paused='0']",
}


def steps_for(action: str, state: ClockState) -> List[str]:
    if action not in _STEPS:
        raise ValueError(f"Unknown clock action: {action!r}")
    return list(_STEPS[action][state.name])


def read_state(page) -> ClockState:
    clock = page.locator(CLOCK)
    clock.wait_for(state="attached", timeout=CONFIRM_TIMEOUT_MS)
    running = clock.get_attribute("data-running") == "1"
    paused = clock.get_attribute("data-paused") == "1"
    return ClockState(running=running or paused, paused=paused)


def _raise_on_save_error(page) -> None:
    panel = page.locator(SAVE_ERROR_PANEL)
    if panel.count() and panel.is_visible():
        message = page.locator(SAVE_ERROR_MESSAGE).inner_text().strip()
        raise RuntimeError(f"Timebutler rejected the time entry: {message or 'unknown error'}")


def _click_stop(page) -> None:
    page.locator(STOP_BUTTON).click()
    confirm = page.locator(STOP_CONFIRM)
    confirm.wait_for(state="visible", timeout=CONFIRM_TIMEOUT_MS)
    confirm.click()


def _click(page, step: str) -> None:
    clickers: Dict[str, Callable[[], None]] = {
        "play": lambda: page.locator(PLAY_BUTTON).click(),
        "pause": lambda: page.locator(PAUSE_BUTTON).click(),
        "resume": lambda: page.locator(RESUME_BUTTON).click(),
        "stop": lambda: _click_stop(page),
    }
    clickers[step]()


def _wait_for_state(page, expected: str) -> None:
    try:
        page.locator(_STATE_SELECTORS[expected]).wait_for(
            state="attached", timeout=CONFIRM_TIMEOUT_MS
        )
    except Exception:
        _raise_on_save_error(page)
        raise RuntimeError(f"Time clock did not switch to '{expected}'.")


def perform(page, action: str, logger: logging.Logger) -> dict:
    """Runs `action` on the clock and returns the states before and after."""
    before = read_state(page)
    steps = steps_for(action, before)
    if not steps:
        logger.info("Clock already %s - nothing to do for '%s'.", before.name, action)
    for step in steps:
        logger.info("Clock %s: clicking '%s'.", read_state(page).name, step)
        _click(page, step)
        _wait_for_state(page, _EXPECTED_AFTER[step])
    after = read_state(page)
    logger.info("Clock action '%s' done: %s -> %s.", action, before.name, after.name)
    return {"action": action, "before": before.name, "after": after.name, "changed": bool(steps)}
