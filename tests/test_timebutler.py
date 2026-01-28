from __future__ import annotations

import logging
from datetime import date, timedelta
from types import SimpleNamespace
from pathlib import Path

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


def test_write_last_run_updates_file(tmp_path, monkeypatch):
    test_file = tmp_path / "last_run.txt"
    monkeypatch.setattr(tb, "LAST_RUN_FILE", test_file)
    tb.write_last_run(DummyLogger())
    assert test_file.read_text(encoding="utf-8") == date.today().isoformat()


def test_get_current_ssid_parses_netsh_output(monkeypatch):
    # Mock return values
    proc_mock = MagicMock()
    proc_mock.returncode = 0
    proc_mock.stdout = """
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
    mock_sub.return_value = proc_mock

    ssid = timebutler_run.get_current_ssid(MagicMock())
    assert ssid == "TestWiFi"
