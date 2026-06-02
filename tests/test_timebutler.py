from __future__ import annotations

import json
import sys
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


def _run_main(monkeypatch, *, run_playwright, ssid="OfficeWiFi"):
    """Drives tb.main() with everything external mocked; returns (exit_code, notifications)."""
    notes = []
    monkeypatch.setattr(sys, "argv", ["timebutler_run.py"])
    monkeypatch.setattr(tb, "ensure_directories", lambda: None)
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
