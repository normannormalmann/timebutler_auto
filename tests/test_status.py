from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import tb_status


def test_get_task_info_parses_json(monkeypatch):
    payload = {"State": "Ready", "LastRunTime": "02.06.2026 13:37:00", "LastTaskResult": 0}
    monkeypatch.setattr(
        tb_status.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr=""),
    )
    assert tb_status.get_task_info() == payload


def test_get_task_info_handles_missing_task(monkeypatch):
    monkeypatch.setattr(
        tb_status.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    assert tb_status.get_task_info() is None


def test_get_task_info_handles_missing_powershell(monkeypatch):
    def raise_fnf(*args, **kwargs):
        raise FileNotFoundError("powershell")

    monkeypatch.setattr(tb_status.subprocess, "run", raise_fnf)
    assert tb_status.get_task_info() is None


def test_build_status_report_healthy(tmp_path):
    last_run = tmp_path / "last_run.txt"
    last_run.write_text(date.today().isoformat(), encoding="utf-8")
    log = tmp_path / "timebutler.log"
    log.write_text("2026-06-02 13:37:00 INFO done\n", encoding="utf-8")
    report = tb_status.build_status_report(
        "OfficeWiFi",
        {"OfficeWiFi"},
        last_run,
        log,
        {"State": "Ready", "LastRunTime": "x", "LastTaskResult": 0},
    )
    assert "OfficeWiFi (erlaubt)" in report
    assert "Heute gestempelt: ja" in report
    assert "OK" in report
    assert "INFO done" in report


def test_build_status_report_failure_code_hex(tmp_path):
    report = tb_status.build_status_report(
        None,
        set(),
        tmp_path / "missing.txt",
        tmp_path / "missing.log",
        {"State": "Ready", "LastRunTime": "x", "LastTaskResult": 2147942667},
    )
    assert "0x8007010B" in report
    assert "nicht verbunden" in report
    assert "Heute gestempelt: nein" in report


def test_build_status_report_missing_task(tmp_path):
    report = tb_status.build_status_report(
        "OfficeWiFi", {"Other"}, tmp_path / "x", tmp_path / "y", None
    )
    assert "nicht registriert" in report
    assert "NICHT in allowed_ssids" in report
