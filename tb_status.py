"""Local-only status report for the Timebutler automation (no browser, no login)."""
from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path
from typing import Optional

TASK_NAME = "TimebutlerAuto"

# Locale-independent task query: schtasks' text output is localized, the
# CIM objects serialized as JSON are not.
_PS_TEMPLATE = (
    "$t = Get-ScheduledTask -TaskName '{name}' -ErrorAction SilentlyContinue; "
    "if ($t) {{ $i = Get-ScheduledTaskInfo -TaskName '{name}'; "
    "[pscustomobject]@{{ State = [string]$t.State; "
    "LastRunTime = [string]$i.LastRunTime; "
    "LastTaskResult = $i.LastTaskResult }} | ConvertTo-Json -Compress }}"
)


def get_task_info(task_name: str = TASK_NAME) -> Optional[dict]:
    """Queries the scheduled task via PowerShell, returns a dict or None.

    task_name is interpolated into a PowerShell command string - pass only
    trusted constants, never user input.
    """
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", _PS_TEMPLATE.format(name=task_name)],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def last_log_line(log_file: Path) -> Optional[str]:
    if not log_file.exists():
        return None
    try:
        lines = log_file.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        return lines[-1] if lines else None
    except OSError:
        return None


def build_status_report(
    ssid: Optional[str],
    allowed_ssids: set,
    last_run_file: Path,
    log_file: Path,
    task_info: Optional[dict],
) -> str:
    lines = ["Timebutler Auto - Status", "-" * 40]

    if ssid:
        allowed = ssid in allowed_ssids or ssid.lower() in {s.lower() for s in allowed_ssids}
        lines.append(f"WLAN: {ssid} ({'erlaubt' if allowed else 'NICHT in allowed_ssids'})")
    else:
        lines.append("WLAN: nicht verbunden / nicht erkennbar")

    stamped = False
    if last_run_file.exists():
        try:
            stamped = last_run_file.read_text(encoding="utf-8").strip() == date.today().isoformat()
        except OSError:
            pass
    lines.append(f"Heute gestempelt: {'ja' if stamped else 'nein'}")

    if task_info:
        result = int(task_info.get("LastTaskResult") or 0)
        health = "OK" if result == 0 else f"FEHLER 0x{result & 0xFFFFFFFF:08X}"
        lines.append(
            f"Task: {task_info.get('State', '?')}, "
            f"letzter Lauf {task_info.get('LastRunTime', '?')} -> {health}"
        )
    else:
        lines.append(f"Task '{TASK_NAME}': nicht registriert")

    log_line = last_log_line(log_file)
    lines.append(f"Letzter Log-Eintrag: {log_line}" if log_line else "Letzter Log-Eintrag: (kein Log)")
    return "\n".join(lines)
