from __future__ import annotations

import pytest

import tb_clock as tc


class DummyLogger:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class FakeClockPage:
    """Simulates the Timebutler UI 3.x time clock and its data attributes."""

    def __init__(self, running="0", paused="0", save_error=None, stuck=False):
        self.attrs = {"data-running": running, "data-paused": paused}
        self.save_error = save_error
        self.stuck = stuck  # clicks have no effect
        self.finish_panel_open = False
        self.clicks = []

    def locator(self, selector):
        return FakeLocator(self, selector)

    def click(self, selector):
        self.clicks.append(selector)
        if self.stuck:
            return
        if selector in (tc.PLAY_BUTTON, tc.RESUME_BUTTON):
            self.attrs.update({"data-running": "1", "data-paused": "0"})
        elif selector == tc.PAUSE_BUTTON:
            self.attrs.update({"data-running": "1", "data-paused": "1"})
        elif selector == tc.STOP_BUTTON:
            self.finish_panel_open = True
        elif selector == tc.STOP_CONFIRM and not self.save_error:
            self.attrs.update({"data-running": "0", "data-paused": "0"})

    def matches(self, selector):
        if selector == tc.CLOCK:
            return True
        if selector == tc.STOP_CONFIRM:
            return self.finish_panel_open
        if selector == tc.SAVE_ERROR_PANEL:
            return bool(self.save_error)
        for state, state_selector in tc._STATE_SELECTORS.items():
            if selector == state_selector:
                return tc.ClockState(
                    running=self.attrs["data-running"] == "1" or self.attrs["data-paused"] == "1",
                    paused=self.attrs["data-paused"] == "1",
                ).name == state
        return False


class FakeLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    def wait_for(self, state="visible", timeout=None):
        if not self.page.matches(self.selector):
            raise TimeoutError(self.selector)

    def get_attribute(self, name):
        return self.page.attrs.get(name)

    def click(self):
        self.page.click(self.selector)

    def count(self):
        return 1 if self.page.matches(self.selector) else 0

    def is_visible(self):
        return self.page.matches(self.selector)

    def inner_text(self):
        return self.page.save_error or ""


@pytest.mark.parametrize(
    "action,state,expected",
    [
        ("start", tc.ClockState(False, False), ["play"]),
        ("start", tc.ClockState(True, False), []),
        ("start", tc.ClockState(True, True), ["resume"]),
        ("pause", tc.ClockState(True, False), ["pause"]),
        ("pause", tc.ClockState(False, False), []),
        ("resume", tc.ClockState(True, True), ["resume"]),
        ("resume", tc.ClockState(True, False), []),
        ("stop", tc.ClockState(True, False), ["stop"]),
        ("stop", tc.ClockState(True, True), ["resume", "stop"]),
        ("stop", tc.ClockState(False, False), []),
    ],
)
def test_steps_for_covers_every_transition(action, state, expected):
    assert tc.steps_for(action, state) == expected


def test_steps_for_rejects_unknown_action():
    with pytest.raises(ValueError):
        tc.steps_for("explode", tc.ClockState(False, False))


def test_read_state_treats_paused_as_running():
    assert tc.read_state(FakeClockPage(running="0", paused="1")) == tc.ClockState(True, True)


def test_full_day_sequence():
    page = FakeClockPage()
    results = [tc.perform(page, a, DummyLogger()) for a in ("start", "pause", "resume", "stop")]
    assert [(r["before"], r["after"]) for r in results] == [
        ("stopped", "running"),
        ("running", "paused"),
        ("paused", "running"),
        ("running", "stopped"),
    ]
    assert page.clicks == [
        tc.PLAY_BUTTON,
        tc.PAUSE_BUTTON,
        tc.RESUME_BUTTON,
        tc.STOP_BUTTON,
        tc.STOP_CONFIRM,
    ]


def test_repeated_action_is_a_noop():
    page = FakeClockPage(running="1")
    result = tc.perform(page, "start", DummyLogger())
    assert result["changed"] is False
    assert page.clicks == []


def test_stop_while_paused_resumes_first():
    page = FakeClockPage(running="1", paused="1")
    result = tc.perform(page, "stop", DummyLogger())
    assert result["after"] == "stopped"
    assert page.clicks[0] == tc.RESUME_BUTTON


def test_stop_reports_timebutler_save_error():
    page = FakeClockPage(running="1", save_error="Buchung gesperrt")
    with pytest.raises(RuntimeError, match="Buchung gesperrt"):
        tc.perform(page, "stop", DummyLogger())


def test_click_without_effect_raises():
    page = FakeClockPage(stuck=True)
    with pytest.raises(RuntimeError, match="did not switch"):
        tc.perform(page, "start", DummyLogger())
