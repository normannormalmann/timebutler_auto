# Failure Notifications, Credential Manager, --status, BOM Tolerance — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Notify on failed punch-ins, move the password into the Windows Credential Manager with automatic migration, add a local-only `--status` command, and make config reading BOM-tolerant.

**Architecture:** Two new focused modules (`tb_credentials.py` for password resolution + migration, `tb_status.py` for the status report) keep `timebutler_run.py` as the thin orchestrator. All new logic is unit-testable without a browser or account; keyring and PowerShell calls are injected/mocked in tests.

**Tech Stack:** Python 3.9+, pytest with monkeypatch, `keyring` (optional at runtime, guarded import), PowerShell `Get-ScheduledTaskInfo | ConvertTo-Json` for locale-independent task health.

**Spec:** `docs/superpowers/specs/2026-06-02-notifications-credentials-status-design.md`

**Conventions:** Repo root is the working directory. Run tests with `python -m pytest` (conftest.py puts the root on sys.path). Commit after every green task. No umlauts in new user-facing strings (console codepage safety).

---

### Task 1: BOM tolerance for settings.json and .env

**Files:**
- Modify: `timebutler_run.py` (function `load_allowed_ssids`)
- Modify: `install.ps1` (the two `Set-Content`/`Out-File`-style writes)
- Test: `tests/test_timebutler.py`

- [ ] **Step 1.1: Write the failing test**

Append to `tests/test_timebutler.py`:

```python
def test_load_allowed_ssids_accepts_bom(tmp_path, monkeypatch):
    # Windows PowerShell 5.1 writes UTF-8 *with* BOM; json.loads chokes on it
    settings = tmp_path / "settings.json"
    settings.write_bytes(b'\xef\xbb\xbf{"allowed_ssids": ["OfficeWiFi"]}')
    monkeypatch.setattr(tb, "SETTINGS_FILE", settings)
    assert tb.load_allowed_ssids(DummyLogger()) == {"OfficeWiFi"}
```

- [ ] **Step 1.2: Run test to verify it fails**

Run: `python -m pytest tests/test_timebutler.py::test_load_allowed_ssids_accepts_bom -v`
Expected: FAIL (returns `set()` because `json.JSONDecodeError` on the BOM)

- [ ] **Step 1.3: Implement**

In `timebutler_run.py`, `load_allowed_ssids`, change the read line:

```python
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8-sig"))
```

(`utf-8-sig` accepts both BOM-prefixed and BOM-less files.)

- [ ] **Step 1.4: Run test to verify it passes**

Run: `python -m pytest tests/test_timebutler.py -v`
Expected: all PASS

- [ ] **Step 1.5: Make install.ps1 write BOM-less**

In `install.ps1` replace the `.env` write:

```powershell
    $envContent = "TIMEBUTLER_USERNAME=$email`r`nTIMEBUTLER_PASSWORD=$pass"
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText((Join-Path (Get-Location).Path ".env"), $envContent, $utf8NoBom)
```

and the settings write:

```powershell
$jsonPayload = @{ allowed_ssids = @($finalSSIDs) } | ConvertTo-Json
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText((Join-Path (Get-Location).Path $settingsPath), $jsonPayload, $utf8NoBom)
```

(Remove the old `Set-Content ... -Encoding utf8` lines they replace.)

- [ ] **Step 1.6: Verify install.ps1 still parses**

Run (PowerShell):
```powershell
$errs = $null; $null = [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path .\install.ps1), [ref]$null, [ref]$errs); $errs.Count
```
Expected: `0`

- [ ] **Step 1.7: Commit**

```bash
git add tests/test_timebutler.py timebutler_run.py install.ps1
git commit -m "Tolerate UTF-8 BOM in settings.json and write config files BOM-less"
```

---

### Task 2: Credential module with keyring + auto-migration

**Files:**
- Create: `tb_credentials.py`
- Modify: `timebutler_run.py` (replace `load_credentials`, drop dotenv import)
- Modify: `requirements.txt`
- Create: `tests/test_credentials.py`

- [ ] **Step 2.1: Write the failing tests**

Create `tests/test_credentials.py`:

```python
from __future__ import annotations

from types import SimpleNamespace

import pytest

import tb_credentials as cred


class DummyLogger:
    def __getattr__(self, name):
        def _noop(*args, **kwargs):
            return None

        return _noop


class FakeKeyring:
    def __init__(self):
        self.store = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password


class BrokenKeyring:
    def get_password(self, *args):
        raise RuntimeError("backend down")

    def set_password(self, *args):
        raise RuntimeError("backend down")


def make_args(username=None, password=None):
    return SimpleNamespace(username=username, password=password)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    # load_dotenv writes os.environ directly (not tracked by monkeypatch),
    # so every test starts by clearing both variables.
    monkeypatch.delenv("TIMEBUTLER_USERNAME", raising=False)
    monkeypatch.delenv("TIMEBUTLER_PASSWORD", raising=False)


def test_cli_password_wins(tmp_path, monkeypatch):
    fake = FakeKeyring()
    fake.set_password("timebutler", "user@example.com", "from-keyring")
    monkeypatch.setattr(cred, "keyring", fake)
    user, pw = cred.load_credentials(
        make_args("user@example.com", "from-cli"), tmp_path, DummyLogger()
    )
    assert (user, pw) == ("user@example.com", "from-cli")


def test_keyring_password_used(tmp_path, monkeypatch):
    fake = FakeKeyring()
    fake.set_password("timebutler", "user@example.com", "from-keyring")
    monkeypatch.setattr(cred, "keyring", fake)
    user, pw = cred.load_credentials(
        make_args("user@example.com"), tmp_path, DummyLogger()
    )
    assert (user, pw) == ("user@example.com", "from-keyring")


def test_env_password_migrates_to_keyring(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "TIMEBUTLER_USERNAME=user@example.com\nTIMEBUTLER_PASSWORD=secret\nOTHER=keep\n",
        encoding="utf-8",
    )
    fake = FakeKeyring()
    monkeypatch.setattr(cred, "keyring", fake)
    user, pw = cred.load_credentials(make_args(), tmp_path, DummyLogger())
    assert (user, pw) == ("user@example.com", "secret")
    assert fake.store[("timebutler", "user@example.com")] == "secret"
    content = env.read_text(encoding="utf-8")
    assert "TIMEBUTLER_PASSWORD" not in content
    assert "OTHER=keep" in content
    assert "TIMEBUTLER_USERNAME=user@example.com" in content


def test_env_fallback_without_keyring(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("TIMEBUTLER_USERNAME=u\nTIMEBUTLER_PASSWORD=p\n", encoding="utf-8")
    monkeypatch.setattr(cred, "keyring", None)
    user, pw = cred.load_credentials(make_args(), tmp_path, DummyLogger())
    assert (user, pw) == ("u", "p")
    # no migration possible -> .env stays untouched
    assert "TIMEBUTLER_PASSWORD" in env.read_text(encoding="utf-8")


def test_broken_keyring_falls_back_to_env(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("TIMEBUTLER_USERNAME=u\nTIMEBUTLER_PASSWORD=p\n", encoding="utf-8")
    monkeypatch.setattr(cred, "keyring", BrokenKeyring())
    user, pw = cred.load_credentials(make_args(), tmp_path, DummyLogger())
    assert (user, pw) == ("u", "p")
    assert "TIMEBUTLER_PASSWORD" in env.read_text(encoding="utf-8")


def test_missing_credentials_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(cred, "keyring", None)
    user, pw = cred.load_credentials(make_args(), tmp_path, DummyLogger())
    assert (user, pw) == (None, None)
```

- [ ] **Step 2.2: Run tests to verify they fail**

Run: `python -m pytest tests/test_credentials.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tb_credentials'`

- [ ] **Step 2.3: Implement tb_credentials.py**

Create `tb_credentials.py`:

```python
"""
Credential handling for the Timebutler automation.

Password resolution order:
1. --password CLI argument (debugging escape hatch)
2. Windows Credential Manager (via keyring, service "timebutler")
3. TIMEBUTLER_PASSWORD from the environment / .env file (fallback)

When a password is found in the environment and keyring is available, it is
migrated into the Credential Manager and removed from the .env file. The
credential store must never block a punch-in: every keyring failure degrades
to the .env value with a warning.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None  # type: ignore

try:
    import keyring
except ImportError:  # pragma: no cover - optional dependency
    keyring = None  # type: ignore

SERVICE_NAME = "timebutler"


def get_stored_password(username: str, logger) -> Optional[str]:
    if keyring is None:
        return None
    try:
        return keyring.get_password(SERVICE_NAME, username)
    except Exception as exc:
        logger.warning("Credential Manager unavailable: %s", exc)
        return None


def store_password(username: str, password: str, logger) -> bool:
    if keyring is None:
        return False
    try:
        keyring.set_password(SERVICE_NAME, username, password)
        return True
    except Exception as exc:
        logger.warning("Could not store password in Credential Manager: %s", exc)
        return False


def remove_password_from_env_file(env_path: Path, logger) -> None:
    """Rewrites the .env file without its TIMEBUTLER_PASSWORD line."""
    if not env_path.exists():
        return
    try:
        lines = env_path.read_text(encoding="utf-8-sig").splitlines()
        kept = [ln for ln in lines if not ln.strip().startswith("TIMEBUTLER_PASSWORD")]
        if len(kept) == len(lines):
            return
        content = "\n".join(kept)
        if content:
            content += "\n"
        env_path.write_text(content, encoding="utf-8")
        logger.info("Removed TIMEBUTLER_PASSWORD from %s.", env_path)
    except OSError as exc:
        logger.warning("Could not rewrite %s: %s", env_path, exc)


def migrate_env_password(env_path: Path, username: str, env_password: str, logger) -> None:
    """Moves a password found in the environment into the Credential Manager."""
    stored = get_stored_password(username, logger)
    if stored == env_password:
        # already migrated earlier; just clean up the .env leftover
        remove_password_from_env_file(env_path, logger)
        return
    if store_password(username, env_password, logger):
        logger.info(
            "Migrated password for '%s' into the Windows Credential Manager.", username
        )
        remove_password_from_env_file(env_path, logger)


def load_credentials(args, base_dir: Path, logger) -> Tuple[Optional[str], Optional[str]]:
    """Returns (username, password); either is None when unresolvable."""
    env_path = base_dir / ".env"
    if load_dotenv is not None:
        load_dotenv(env_path, encoding="utf-8-sig")

    username = args.username or os.getenv("TIMEBUTLER_USERNAME")
    if not username:
        return None, None

    if args.password:
        return username, args.password

    env_password = os.getenv("TIMEBUTLER_PASSWORD")
    if env_password and keyring is not None:
        migrate_env_password(env_path, username, env_password, logger)

    password = get_stored_password(username, logger) or env_password
    return username, password
```

- [ ] **Step 2.4: Run tests to verify they pass**

Run: `python -m pytest tests/test_credentials.py -v`
Expected: all 6 PASS

- [ ] **Step 2.5: Rewire timebutler_run.py**

In `timebutler_run.py`:

1. Delete the dotenv import block at the top:
```python
try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None  # type: ignore
```

2. Add below the tb_selectors import:
```python
import tb_credentials
```

3. Delete the whole `load_credentials` function (it moved to tb_credentials).

4. In `main()`, replace
```python
    username, password = load_credentials(args, logger)
```
with
```python
    username, password = tb_credentials.load_credentials(args, BASE_DIR, logger)
    if not username or not password:
        logger.error(
            "Missing credentials. Provide TIMEBUTLER_USERNAME and TIMEBUTLER_PASSWORD "
            "(.env) or store the password in the Windows Credential Manager."
        )
        show_notification(
            "Timebutler Auto", "Zugangsdaten fehlen - bitte Konfiguration pruefen."
        )
        return 2
```

(Note: the old function called `sys.exit(2)` itself; returning 2 keeps the same
process exit code via `sys.exit(main())` and makes main() testable.)

5. Add `keyring>=25` as a new line in `requirements.txt`.

- [ ] **Step 2.6: Run the full suite**

Run: `python -m pytest -v`
Expected: all PASS (old credential tests do not exist; nothing else touches load_credentials)

- [ ] **Step 2.7: Commit**

```bash
git add tb_credentials.py tests/test_credentials.py timebutler_run.py requirements.txt
git commit -m "Store password in Windows Credential Manager with .env auto-migration"
```

---

### Task 3: Failure notifications

**Files:**
- Modify: `timebutler_run.py` (`main()` except branch)
- Test: `tests/test_timebutler.py`

- [ ] **Step 3.1: Write the failing tests**

Append to `tests/test_timebutler.py` (also add `import sys` to the imports at the top):

```python
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
```

- [ ] **Step 3.2: Run tests to verify the failure test fails**

Run: `python -m pytest tests/test_timebutler.py::test_main_notifies_on_failure tests/test_timebutler.py::test_main_no_notification_on_ssid_skip -v`
Expected: `test_main_notifies_on_failure` FAILS (no notification yet), skip test PASSES

- [ ] **Step 3.3: Implement**

In `timebutler_run.py`, `main()`, extend the except branch:

```python
    try:
        run_playwright(ctx, username, password)
    except Exception as exc:
        logger.exception("Automation failed: %s", exc)
        show_notification(
            "Timebutler Auto", "Einstempeln fehlgeschlagen! Details: logs\\timebutler.log"
        )
        return 1
```

- [ ] **Step 3.4: Run tests to verify they pass**

Run: `python -m pytest tests/test_timebutler.py -v`
Expected: all PASS

- [ ] **Step 3.5: Commit**

```bash
git add tests/test_timebutler.py timebutler_run.py
git commit -m "Show a Windows notification when the punch-in fails"
```

---

### Task 4: tb_status.py and --status

**Files:**
- Create: `tb_status.py`
- Modify: `timebutler_run.py` (`parse_args`, `main()`)
- Create: `tests/test_status.py`
- Test (extend): `tests/test_timebutler.py`

- [ ] **Step 4.1: Write the failing tests**

Create `tests/test_status.py`:

```python
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
```

Append to `tests/test_timebutler.py`:

```python
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
```

- [ ] **Step 4.2: Run tests to verify they fail**

Run: `python -m pytest tests/test_status.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tb_status'`

- [ ] **Step 4.3: Implement tb_status.py**

Create `tb_status.py`:

```python
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
        result = int(task_info.get("LastTaskResult", 0))
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
```

- [ ] **Step 4.4: Wire it into timebutler_run.py**

1. Add below `import tb_credentials`:
```python
import tb_status
```

2. In `parse_args()`, add:
```python
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print a local status report (Wi-Fi, last run, task health) and exit.",
    )
```

3. In `main()`, directly after `logger = init_logging(debug=args.debug)`:
```python
    if args.status:
        report = tb_status.build_status_report(
            get_current_ssid(logger),
            load_allowed_ssids(logger),
            LAST_RUN_FILE,
            LOG_FILE,
            tb_status.get_task_info(),
        )
        print(report)
        return 0
```

- [ ] **Step 4.5: Run all tests**

Run: `python -m pytest -v`
Expected: all PASS

- [ ] **Step 4.6: Manual smoke test**

Run: `python timebutler_run.py --status`
Expected output (values vary): WLAN line, "Heute gestempelt: ja", Task "Ready ... OK", last log line. Must finish in about a second and must not open a browser.

- [ ] **Step 4.7: Commit**

```bash
git add tb_status.py tests/test_status.py tests/test_timebutler.py timebutler_run.py
git commit -m "Add local-only --status command"
```

---

### Task 5: Docs, dependency on this machine, push

**Files:**
- Modify: `README.md`
- Machine setup (not committed): install keyring into the Python the task uses

- [ ] **Step 5.1: Install keyring for the system Python (the scheduled task uses it)**

Run: `C:\Python314\python.exe -m pip install --user keyring`
Expected: successful install (playwright already lives in the same user site-packages).

- [ ] **Step 5.2: Verify migration on this machine**

Run: `python timebutler_run.py --status` (still fine), then `python -c "import keyring; print(bool(keyring.get_password('timebutler', __import__('os').getenv('TIMEBUTLER_USERNAME') or '')))"` after one normal run has migrated the password.
Note: the actual migration happens on the next real punch-in run; do not force a punch-in just for this. Checking that `.env` no longer contains `TIMEBUTLER_PASSWORD` after tomorrow's run is sufficient.

- [ ] **Step 5.3: Update README**

- Features list: add "**Failure Notifications**: Windows notification when a punch-in fails." and "**Credential Manager**: The password is stored DPAPI-encrypted in the Windows Credential Manager; an existing `.env` password is migrated automatically on first run."
- Usage section: document `--status` with one example output block.
- Configuration section: note that `.env` only needs `TIMEBUTLER_USERNAME` after migration; `TIMEBUTLER_PASSWORD` is honored as fallback.

- [ ] **Step 5.4: Full suite + commit + push**

Run: `python -m pytest -v`
Expected: all PASS

```bash
git add README.md
git commit -m "Document failure notifications, credential manager and --status"
git push
```

---

## Self-Review Notes

- Spec coverage: §1 → Task 3, §2 → Task 2, §3 → Task 4, §4 → Task 1, testing section → Steps x.1 in every task. No gaps.
- `.env` reading with `utf-8-sig` (spec §4) is implemented inside `tb_credentials.load_credentials` (Task 2, `load_dotenv(env_path, encoding="utf-8-sig")`).
- Type consistency: `load_credentials(args, base_dir, logger) -> (Optional[str], Optional[str])` is used identically in Task 2 impl, Task 2 rewiring, and the Task 3/4 test helpers.
- CI installs only `pytest python-dotenv`; all keyring/PowerShell interaction is mocked, so the suite stays green on Ubuntu.
