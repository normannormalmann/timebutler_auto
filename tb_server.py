"""
HTTP API that lets n8n drive the Timebutler time recorder.

n8n does the scheduling (cron + wait nodes); this service only knows how to
compute the daily plan and how to click the clock buttons in a headless
browser. Endpoints (all JSON, all but /health need `Authorization: Bearer`):

    GET  /health                   liveness probe
    GET  /plan[?date=YYYY-MM-DD]   today's (or the given day's) plan
    GET  /clock                    current clock state
    POST /clock/{start|pause|resume|stop}

Responses use the envelope {"success": bool, "data": ..., "error": str|null}.
/health is always answered immediately; all other requests are serialized
by a lock, so two clock actions never race.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import sys
import threading
from dataclasses import dataclass
from datetime import date, datetime, tzinfo
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Mapping, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import tb_clock
import tb_schedule

MIN_TOKEN_LENGTH = 24
DEFAULT_PORT = 8080
DEFAULT_TIMEZONE = "Europe/Berlin"

logger = logging.getLogger("timebutler.server")


class ClientError(Exception):
    def __init__(self, status: HTTPStatus, message: str):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class App:
    token: str
    plan_for: Callable[[date], dict]
    run_clock: Callable[[str], dict]  # action name or "status"
    today: Callable[[], date]


def _authorized(app: App, header: Optional[str]) -> bool:
    if not header or not header.startswith("Bearer "):
        return False
    return hmac.compare_digest(header[len("Bearer "):].encode(), app.token.encode())


def _parse_day(app: App, query: Mapping[str, list]) -> date:
    raw = query.get("date", [None])[0]
    if raw is None:
        return app.today()
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise ClientError(HTTPStatus.BAD_REQUEST, "date must be YYYY-MM-DD")


def route(app: App, method: str, raw_path: str, auth_header: Optional[str]) -> Tuple[HTTPStatus, dict]:
    """Dispatches one request; returns (status, data). Raises ClientError."""
    url = urlparse(raw_path)
    path = url.path.rstrip("/") or "/"

    if method == "GET" and path == "/health":
        return HTTPStatus.OK, {"status": "ok"}
    if not _authorized(app, auth_header):
        raise ClientError(HTTPStatus.UNAUTHORIZED, "missing or invalid bearer token")

    if path in ("/plan", "/clock") and method != "GET":
        raise ClientError(HTTPStatus.METHOD_NOT_ALLOWED, f"use GET for {path}")
    if path == "/plan":
        return HTTPStatus.OK, app.plan_for(_parse_day(app, parse_qs(url.query)))
    if path == "/clock":
        return HTTPStatus.OK, app.run_clock("status")
    if path.startswith("/clock/"):
        action = path[len("/clock/"):]
        if action not in tb_clock.ACTIONS:
            raise ClientError(HTTPStatus.NOT_FOUND, f"unknown action '{action}'")
        if method != "POST":
            raise ClientError(HTTPStatus.METHOD_NOT_ALLOWED, "use POST for clock actions")
        if action == "start":
            # a day may have been skipped after n8n fetched the plan
            plan = app.plan_for(app.today())
            if not plan.get("work"):
                return HTTPStatus.OK, {"action": action, "changed": False, "skipped": plan.get("reason")}
        return HTTPStatus.OK, app.run_clock(action)
    raise ClientError(HTTPStatus.NOT_FOUND, "not found")


def make_handler(app: App):
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        server_version = "TimebutlerClock/1.0"

        def _send(self, status: HTTPStatus, body: dict) -> None:
            payload = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _handle(self, method: str) -> None:
            try:
                auth = self.headers.get("Authorization")
                if urlparse(self.path).path.rstrip("/") == "/health":
                    status, data = route(app, method, self.path, auth)
                else:
                    with lock:
                        status, data = route(app, method, self.path, auth)
                self._send(status, {"success": True, "data": data, "error": None})
            except ClientError as exc:
                self._send(exc.status, {"success": False, "data": None, "error": str(exc)})
            except Exception:
                logger.exception("Request %s %s failed", method, self.path)
                self._send(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"success": False, "data": None, "error": "clock action failed, see server log"},
                )

        def do_GET(self) -> None:  # noqa: N802 - http.server naming
            self._handle("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._handle("POST")

        def log_message(self, fmt: str, *args) -> None:
            logger.info("%s - %s", self.address_string(), fmt % args)

    return Handler


def _holiday_lookup(region: Optional[str]) -> Optional[tb_schedule.HolidayLookup]:
    """TB_HOLIDAY_REGION like 'DE' or 'DE-BY' (country-subdivision)."""
    if not region:
        return None
    import holidays  # optional dependency, only needed when configured

    country, _, subdiv = region.partition("-")
    calendar = holidays.country_holidays(country, subdiv=subdiv or None)
    return lambda day: calendar.get(day)


def _load_timezone(name: str) -> tzinfo:
    from zoneinfo import ZoneInfo

    return ZoneInfo(name)


def build_app(env: Mapping[str, str]) -> App:
    token = env.get("TB_API_TOKEN", "")
    if len(token) < MIN_TOKEN_LENGTH:
        raise SystemExit(f"TB_API_TOKEN must be set and at least {MIN_TOKEN_LENGTH} characters long.")
    username = env.get("TIMEBUTLER_USERNAME")
    password = env.get("TIMEBUTLER_PASSWORD")
    if not username or not password:
        raise SystemExit("TIMEBUTLER_USERNAME and TIMEBUTLER_PASSWORD must be set.")

    base_dir = Path(__file__).resolve().parent
    state_dir = Path(env.get("TB_STATE_DIR") or base_dir / "state")
    state_dir.mkdir(parents=True, exist_ok=True)
    skip_file = Path(env.get("TB_SKIP_DATES_FILE") or base_dir / "config" / "skip_dates.txt")
    tz = _load_timezone(env.get("TB_TIMEZONE") or DEFAULT_TIMEZONE)
    holiday_lookup = _holiday_lookup(env.get("TB_HOLIDAY_REGION"))
    store = tb_schedule.PlanStore(state_dir / "plan.json")
    tb_schedule.config_from_env(env)  # fail fast on a broken schedule config

    def plan_for(day: date) -> dict:
        # re-read on every call so edits to the skip file apply without a restart
        config = tb_schedule.config_from_env(env, tb_schedule.load_skip_dates(skip_file))
        return tb_schedule.plan_for_day(day, config, tz, store, holiday_lookup)

    def run_clock(action: str) -> dict:
        import tb_session  # imports Playwright lazily

        with tb_session.dashboard_page(
            username, password, state_dir / "storage_state.json", logger
        ) as page:
            if action == "status":
                return {"state": tb_clock.read_state(page).name}
            return tb_clock.perform(page, action, logger)

    return App(
        token=token,
        plan_for=plan_for,
        run_clock=run_clock,
        today=lambda: datetime.now(tz).date(),
    )


def main() -> int:
    logging.basicConfig(
        level=logging.DEBUG if os.getenv("TB_DEBUG") else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    app = build_app(os.environ)
    host = os.getenv("TB_HOST", "0.0.0.0")
    port = int(os.getenv("TB_PORT", DEFAULT_PORT))
    server = ThreadingHTTPServer((host, port), make_handler(app))
    logger.info("Timebutler clock server listening on %s:%s", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
