# Design: Failure Notifications, Credential Manager, --status, BOM Tolerance

Date: 2026-06-02
Status: approved

## Goal

Three user-facing improvements plus one latent bug fix for the Timebutler
auto-punch tool. No behavior change for the happy path (SSID match → punch in
once per day).

## 1. Failure Notifications

**Problem:** `show_notification` fires only on success. When the run fails
(changed password, UI change at Timebutler), the task runs headless via
`pythonw.exe` and the user notices days later.

**Design:**
- `main()` shows a Windows balloon notification on every fatal exit:
  - Automation failure (currently `return 1`): "Einstempeln fehlgeschlagen —
    Details in logs\timebutler.log"
  - Missing credentials (currently `sys.exit(2)` in `load_credentials`):
    dedicated message pointing at `.env` / credential setup.
- No notification for normal skips (wrong SSID, already ran today, SSID
  undetectable) — those are everyday occurrences, not errors.
- Reuse the existing `show_notification` (PowerShell NotifyIcon balloon); no
  new dependency. Notification errors stay swallowed (best effort) so the
  notifier can never crash the run.

## 2. Credentials in Windows Credential Manager (auto-migration)

**Problem:** The password sits in plain text in `.env`.

**Design:**
- New dependency: `keyring` (uses the DPAPI-encrypted Windows Credential
  Locker on Windows). Added to `requirements.txt`.
- Password resolution order in `load_credentials`:
  1. `--password` CLI argument (debugging escape hatch, unchanged)
  2. `keyring.get_password("timebutler", username)`
  3. `TIMEBUTLER_PASSWORD` from the environment / `.env` (fallback)
- Auto-migration on startup: when a password is found in the environment
  AND the Credential Manager has no (or a different) entry for the username:
  - `keyring.set_password("timebutler", username, password)`
  - Rewrite `.env` without the `TIMEBUTLER_PASSWORD` line (username stays;
    preserve all other lines verbatim; write UTF-8 without BOM)
  - Log an INFO line documenting the migration.
- Graceful degradation: if `keyring` is not importable or its backend errors,
  log a warning and continue with the `.env` value. Never block a punch-in
  because of the credential store.
- `install.ps1` stays as-is (writes `.env`); migration happens transparently
  on the first run.

## 3. `--status` Command (local-only)

**Problem:** No way to see at a glance whether the setup is healthy.

**Design:** `python timebutler_run.py --status` prints a short report and
exits 0 without launching a browser or stamping anything:
- Current SSID and whether it is in `allowed_ssids`
- Whether today's run already happened (`state/last_run.txt`)
- Scheduled task health: `LastRunTime` / `LastTaskResult` / `State`, read via
  `powershell Get-ScheduledTask(Info) ... | ConvertTo-Json` (locale-independent,
  unlike `schtasks` text output). Task name configurable, default
  "TimebutlerAuto". Missing task is reported, not an error.
- Last line of `logs/timebutler.log`, if present.
- `--status` short-circuits before credential loading, so it works without
  configured credentials.

## 4. Bug Fix: BOM Tolerance

**Problem:** Windows PowerShell 5.1 `-Encoding utf8` always writes a BOM.
`json.loads` fails on a BOM-prefixed `settings.json`; `python-dotenv` can
mangle the first key of a BOM-prefixed `.env`.

**Design (defense in depth):**
- Python reads `settings.json` and `.env` with `encoding="utf-8-sig"`
  (accepts both BOM and BOM-less).
- `install.ps1` writes `.env` and `settings.json` BOM-less via
  `[System.IO.File]::WriteAllText(..., UTF8Encoding($false))`.

## Testing

Unit tests (no browser, no account, CI-compatible):
- Password resolution order incl. keyring hit/miss (keyring mocked)
- Auto-migration: keyring receives the password, `.env` rewritten without the
  password line, other lines preserved (against `tmp_path`)
- Migration skipped cleanly when keyring is unavailable
- `--status` building blocks: task info JSON parsing (subprocess mocked),
  report assembly
- Failure notification triggered on automation failure, not on SSID skip
  (`show_notification` mocked)
- `load_allowed_ssids` accepts a BOM-prefixed settings file

## Out of Scope

- Auto punch-out (rejected: too error-prone for time accounting)
- Online check of running time recording in `--status` (rejected: keep it fast)
- Toast notifications / BurntToast (balloon works, no new dependency)
