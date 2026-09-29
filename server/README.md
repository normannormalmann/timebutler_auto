# Timebutler Auto — n8n Mode

Instead of reacting to Wi-Fi on your laptop, n8n drives the full workday on a server:

| Step | When (defaults) |
|---|---|
| Punch in | random minute between **09:00 and 09:30** |
| Start break | random minute between **12:00 and 13:00** |
| End break | exactly **30 minutes** later |
| Punch out | **7.5–9 hours** after punching in (break included, so 7–8.5 h of net work) |

Weekends, public holidays (optional) and dates in `config/skip_dates.txt` are skipped.

**Architecture:** n8n cannot run a browser itself, so a small container ([`tb_server.py`](tb_server.py), Playwright + Chromium) exposes the clock as an HTTP API. The n8n workflow fetches the day's plan at 08:45 and uses *Wait* nodes to call the API at the planned times. Plans are persisted, so retries always see the same times, and every clock action is idempotent (starting a running clock is a no-op).

```
n8n (cron 08:45 Mon–Fri) ──GET /plan──▶ timebutler-clock ──Playwright──▶ Timebutler
      └─ Wait ▶ POST /clock/start ▶ Wait ▶ /pause ▶ Wait ▶ /resume ▶ Wait ▶ /stop
```

## 1. Start the clock server (next to n8n)

```bash
cd server
cp .env.sample .env                                    # fill in credentials and TB_API_TOKEN
cp config/skip_dates.sample.txt config/skip_dates.txt  # optional
N8N_NETWORK=n8n_default docker compose up -d --build
```

The image is built from the repository root (the login code in `tb_session.py` / `tb_selectors.py` is shared with the Windows mode); `docker-compose.yml` takes care of that.

`N8N_NETWORK` must be the Docker network your n8n container is on (`docker network ls`). The server publishes no port; n8n reaches it at `http://timebutler-clock:8080`. For n8n Cloud, put the server behind an HTTPS reverse proxy instead and keep the token secret.

Generate the token with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

## 2. Import the n8n workflow

1. In n8n: **Credentials → New → Header Auth**, name `Timebutler Clock Token`, header name `Authorization`, value `Bearer <TB_API_TOKEN>`.
2. **Workflows → Import from file** → [`n8n/timebutler_workflow.json`](n8n/timebutler_workflow.json).
3. Select the credential in each HTTP node; adjust `base_url` in the *Konfiguration* node if needed.
4. Activate the workflow. Optionally set an *Error Workflow* (workflow settings) to get notified on failures.

## API

All endpoints except `/health` require `Authorization: Bearer <TB_API_TOKEN>`. Responses: `{"success": bool, "data": ..., "error": str|null}`.

| Endpoint | Purpose |
|---|---|
| `GET /health` | liveness probe |
| `GET /plan[?date=YYYY-MM-DD]` | the day's plan, or `{"work": false, "reason": ...}` |
| `GET /clock` | current state: `running`, `paused` or `stopped` |
| `POST /clock/start` · `/pause` · `/resume` · `/stop` | clock actions (idempotent) |

## Settings (`server/.env`)

| Variable | Default | Meaning |
|---|---|---|
| `TB_START_WINDOW` | `09:00-09:30` | punch-in window |
| `TB_SHIFT_HOURS` | `7.5-9` | punch-in → punch-out, break included |
| `TB_BREAK_MINUTES` | `30` | break length |
| `TB_BREAK_WINDOW` | `12:00-13:00` | break start window |
| `TB_WORKDAYS` | `1,2,3,4,5` | ISO weekdays (Mon = 1) |
| `TB_HOLIDAY_REGION` | – | skip public holidays, e.g. `DE-BY`, `DE-NW` |
| `TB_TIMEZONE` | `Europe/Berlin` | timezone of the plan |

Invalid combinations are rejected at startup — for example a break that could start more than 6 hours after punching in (German working-time law).

`server/config/skip_dates.txt` takes one date (`2026-12-24`) or range (`2026-10-05..2026-10-09`) per line and is re-read on every plan request — add vacation or sick days there. Adding *today* after the workflow started is fine too: `/clock/start` checks the plan again and refuses to punch in.

## Run without Docker (debugging)

```bash
pip install -r server/requirements.txt && playwright install chromium
TB_API_TOKEN=... TIMEBUTLER_USERNAME=... TIMEBUTLER_PASSWORD=... python server/tb_server.py
```

State (session cookies, plans) goes to `server/state/`, which is git-ignored.

## Notes from live testing

- The clock's `data-running` / `data-paused` attributes are rendered by the server only, so every click is confirmed by reloading the page.
- Accounts without projects/categories save a stop directly (no "Fast geschafft!" dialog); both variants are handled.
- Timebutler does not seem to save entries shorter than about one minute — irrelevant for real days, but keep it in mind when testing stop right after start.
