from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, timedelta
from types import SimpleNamespace

import timebutler_run as tb


class DummyLogger:
    def __getattr__(self, name):
        def _noop(*args, **kwargs):
            return None

        return _noop


def test_already_ran_today_detects_same_day(tmp_path, monkeypatch):
    test_file = tmp_path / "last_run.txt"
    test_file.write_text(date.today().isoformat(), encoding="utf-8")
    monkeypatch.setattr(tb, "LAST_RUN_FILE", test_file)
    assert tb.already_ran_today(False, DummyLogger()) is True


def test_already_ran_today_ignores_old_date(tmp_path, monkeypatch):
    test_file = tmp_path / "last_run.txt"
    yesterday = date.today() - timedelta(days=1)
    test_file.write_text(yesterday.isoformat(), encoding="utf-8")
    monkeypatch.setattr(tb, "LAST_RUN_FILE", test_file)
    assert tb.already_ran_today(False, DummyLogger()) is False


def test_already_ran_today_force_overrides(tmp_path, monkeypatch):
    test_file = tmp_path / "last_run.txt"
    test_file.write_text(date.today().isoformat(), encoding="utf-8")
    monkeypatch.setattr(tb, "LAST_RUN_FILE", test_file)
    assert tb.already_ran_today(True, DummyLogger()) is False


def test_write_last_run_updates_file(tmp_path, monkeypatch):
    test_file = tmp_path / "last_run.txt"
    monkeypatch.setattr(tb, "LAST_RUN_FILE", test_file)
    tb.write_last_run(DummyLogger())
    assert test_file.read_text(encoding="utf-8") == date.today().isoformat()


NETSH_OUTPUT = """
Interface name: Wi-Fi
There are 1 interfaces on the system:

    Name                   : Wi-Fi
    Description            : Intel(R) Wi-Fi 6 AX200 160MHz
    GUID                   : ...
    Physical address       : ...
    State                  : connected
    SSID                   : TestWiFi
    BSSID                  : ...
    Network type           : Infrastructure
    Radio type             : 802.11ax
    Authentication         : WPA2-Personal
    Cipher                 : CCMP
    Connection mode        : Profile
    Channel                : 36
    Receive rate (Mbps)    : 1201
    Transmit rate (Mbps)   : 1201
    Signal                 : 99%
    Profile                : TestWiFi

    Hosted network status  : Not available
"""


def _fake_run(stdout: str, returncode: int = 0):
    def run(*args, **kwargs):
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")

    return run


def test_get_current_ssid_parses_netsh_output(monkeypatch):
    monkeypatch.setattr(tb.subprocess, "run", _fake_run(NETSH_OUTPUT))
    assert tb.get_current_ssid(DummyLogger()) == "TestWiFi"


def test_get_current_ssid_ignores_bssid_line(monkeypatch):
    # The SSID regex must not be confused by the BSSID line.
    output = "    BSSID                  : aa:bb:cc\n    SSID                   : Büro-WLAN\n"
    monkeypatch.setattr(tb.subprocess, "run", _fake_run(output))
    assert tb.get_current_ssid(DummyLogger()) == "Büro-WLAN"


def test_get_current_ssid_handles_netsh_failure(monkeypatch):
    monkeypatch.setattr(tb.subprocess, "run", _fake_run("", returncode=1))
    assert tb.get_current_ssid(DummyLogger()) is None


def test_get_current_ssid_handles_missing_ssid(monkeypatch):
    monkeypatch.setattr(tb.subprocess, "run", _fake_run("State : disconnected\n"))
    assert tb.get_current_ssid(DummyLogger()) is None


def test_load_allowed_ssids_reads_settings(tmp_path, monkeypatch):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"allowed_ssids": ["OfficeWiFi", "GuestWiFi"]}), encoding="utf-8"
    )
    monkeypatch.setattr(tb, "SETTINGS_FILE", settings)
    assert tb.load_allowed_ssids(DummyLogger()) == {"OfficeWiFi", "GuestWiFi"}


def test_load_allowed_ssids_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(tb, "SETTINGS_FILE", tmp_path / "missing.json")
    assert tb.load_allowed_ssids(DummyLogger()) == set()


def test_load_allowed_ssids_invalid_json(tmp_path, monkeypatch):
    settings = tmp_path / "settings.json"
    settings.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(tb, "SETTINGS_FILE", settings)
    assert tb.load_allowed_ssids(DummyLogger()) == set()


def test_load_allowed_ssids_accepts_bom(tmp_path, monkeypatch):
    # Windows PowerShell 5.1 writes UTF-8 *with* BOM; json.loads chokes on it
    settings = tmp_path / "settings.json"
    settings.write_bytes(b'\xef\xbb\xbf{"allowed_ssids": ["OfficeWiFi"]}')
    monkeypatch.setattr(tb, "SETTINGS_FILE", settings)
    assert tb.load_allowed_ssids(DummyLogger()) == {"OfficeWiFi"}


def _aged_file(path, days):
    path.write_text("x", encoding="utf-8")
    old = time.time() - days * 86400
    os.utime(path, (old, old))


def test_cleanup_removes_old_error_artifacts(tmp_path):
    old_html = tmp_path / "error_20260101_000000.html"
    old_png = tmp_path / "error_20260101_000000.png"
    fresh_html = tmp_path / "error_20260609_120000.html"
    _aged_file(old_html, 31)
    _aged_file(old_png, 31)
    _aged_file(fresh_html, 1)

    tb.cleanup_old_artifacts(tmp_path, DummyLogger())

    assert not old_html.exists()
    assert not old_png.exists()
    assert fresh_html.exists()


def test_cleanup_keeps_non_error_files(tmp_path):
    # storage_state.json and last_run.txt age past 30 days but must survive
    state = tmp_path / "storage_state.json"
    last_run = tmp_path / "last_run.txt"
    _aged_file(state, 90)
    _aged_file(last_run, 90)

    tb.cleanup_old_artifacts(tmp_path, DummyLogger())

    assert state.exists()
    assert last_run.exists()


def test_cleanup_missing_dir_is_noop(tmp_path):
    tb.cleanup_old_artifacts(tmp_path / "does_not_exist", DummyLogger())


def test_cleanup_survives_delete_errors(tmp_path, monkeypatch):
    doomed = tmp_path / "error_20260101_000000.html"
    _aged_file(doomed, 40)

    def deny_unlink(self, *args, **kwargs):
        raise OSError("file locked")

    monkeypatch.setattr(type(doomed), "unlink", deny_unlink)
    tb.cleanup_old_artifacts(tmp_path, DummyLogger())  # must not raise


def _run_main(monkeypatch, *, run_playwright, ssid="OfficeWiFi"):
    """Drives tb.main() with everything external mocked; returns (exit_code, notifications)."""
    notes = []
    monkeypatch.setattr(sys, "argv", ["timebutler_run.py"])
    monkeypatch.setattr(tb, "ensure_directories", lambda: None)
    monkeypatch.setattr(tb, "cleanup_old_artifacts", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(tb, "init_logging", lambda debug: DummyLogger())
    monkeypatch.setattr(
        tb.tb_credentials, "load_credentials", lambda a, b, l: ("u", "p")
    )
    monkeypatch.setattr(tb, "load_allowed_ssids", lambda l: {"OfficeWiFi"})
    monkeypatch.setattr(tb, "get_current_ssid", lambda l: ssid)
    monkeypatch.setattr(tb, "already_ran_today", lambda f, l: False)
    monkeypatch.setattr(tb, "write_last_run", lambda l: None)
    monkeypatch.setattr(tb, "run_playwright", run_playwright)
    monkeypatch.setattr(tb, "show_notification", lambda t, m: notes.append(m))
    return tb.main(), notes


def test_main_runs_artifact_cleanup(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "argv", ["timebutler_run.py"])
    monkeypatch.setattr(tb, "ensure_directories", lambda: None)
    monkeypatch.setattr(
        tb, "cleanup_old_artifacts", lambda *a, **k: calls.append(a), raising=False
    )
    monkeypatch.setattr(tb, "init_logging", lambda debug: DummyLogger())
    monkeypatch.setattr(
        tb.tb_credentials, "load_credentials", lambda a, b, l: ("u", "p")
    )
    monkeypatch.setattr(tb, "load_allowed_ssids", lambda l: {"OfficeWiFi"})
    monkeypatch.setattr(tb, "get_current_ssid", lambda l: "OfficeWiFi")
    monkeypatch.setattr(tb, "already_ran_today", lambda f, l: False)
    monkeypatch.setattr(tb, "write_last_run", lambda l: None)
    monkeypatch.setattr(tb, "run_playwright", lambda *a: None)
    monkeypatch.setattr(tb, "show_notification", lambda t, m: None)

    assert tb.main() == 0
    assert calls  # main must trigger the artifact cleanup


def test_main_notifies_on_failure(monkeypatch):
    def boom(ctx, username, password):
        raise RuntimeError("login broken")

    code, notes = _run_main(monkeypatch, run_playwright=boom)
    assert code == 1
    assert any("fehlgeschlagen" in n for n in notes)


def test_main_no_notification_on_ssid_skip(monkeypatch):
    code, notes = _run_main(
        monkeypatch, run_playwright=lambda *a: None, ssid="ElsewhereWiFi"
    )
    assert code == 0
    assert notes == []


def test_main_status_short_circuits(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["timebutler_run.py", "--status"])
    monkeypatch.setattr(tb, "ensure_directories", lambda: None)
    monkeypatch.setattr(tb, "cleanup_old_artifacts", lambda *a, **k: None)
    monkeypatch.setattr(tb, "init_logging", lambda debug: DummyLogger())
    monkeypatch.setattr(tb, "load_allowed_ssids", lambda l: set())
    monkeypatch.setattr(tb, "get_current_ssid", lambda l: None)
    monkeypatch.setattr(tb.tb_status, "get_task_info", lambda: None)
    called = []
    monkeypatch.setattr(
        tb.tb_credentials,
        "load_credentials",
        lambda *a: called.append(1) or ("u", "p"),
    )
    assert tb.main() == 0
    assert called == []  # --status must not touch credentials
    assert "Timebutler Auto - Status" in capsys.readouterr().out
