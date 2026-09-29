from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from datetime import date
from http import HTTPStatus
from http.server import ThreadingHTTPServer

import pytest

import tb_server as srv

TOKEN = "t" * 32
AUTH = f"Bearer {TOKEN}"


def make_app(calls=None, clock_error=None, work=True):
    calls = [] if calls is None else calls

    def run_clock(action):
        calls.append(action)
        if clock_error:
            raise clock_error
        return {"action": action}

    return srv.App(
        token=TOKEN,
        plan_for=lambda day: {"date": day.isoformat(), "work": work, "reason": "skip date"},
        run_clock=run_clock,
        today=lambda: date(2026, 9, 30),
    )


def test_health_needs_no_token():
    assert srv.route(make_app(), "GET", "/health", None) == (HTTPStatus.OK, {"status": "ok"})


@pytest.mark.parametrize("header", [None, "Bearer wrong", TOKEN, f"Basic {TOKEN}"])
def test_protected_routes_reject_bad_tokens(header):
    calls = []
    with pytest.raises(srv.ClientError) as err:
        srv.route(make_app(calls), "POST", "/clock/start", header)
    assert err.value.status == HTTPStatus.UNAUTHORIZED
    assert calls == []


def test_plan_defaults_to_today_and_accepts_date():
    app = make_app()
    assert srv.route(app, "GET", "/plan", AUTH)[1]["date"] == "2026-09-30"
    assert srv.route(app, "GET", "/plan?date=2026-10-01", AUTH)[1]["date"] == "2026-10-01"


def test_plan_rejects_malformed_date():
    with pytest.raises(srv.ClientError) as err:
        srv.route(make_app(), "GET", "/plan?date=tomorrow", AUTH)
    assert err.value.status == HTTPStatus.BAD_REQUEST


def test_clock_routes_dispatch_actions():
    calls = []
    app = make_app(calls)
    for action in ("start", "pause", "resume", "stop"):
        srv.route(app, "POST", f"/clock/{action}", AUTH)
    srv.route(app, "GET", "/clock", AUTH)
    assert calls == ["start", "pause", "resume", "stop", "status"]


def test_start_is_refused_on_non_work_day():
    calls = []
    status, data = srv.route(make_app(calls, work=False), "POST", "/clock/start", AUTH)
    assert status == HTTPStatus.OK
    assert data == {"action": "start", "changed": False, "skipped": "skip date"}
    assert calls == []


def test_stop_still_runs_on_non_work_day():
    calls = []
    srv.route(make_app(calls, work=False), "POST", "/clock/stop", AUTH)
    assert calls == ["stop"]


def test_clock_action_requires_post():
    with pytest.raises(srv.ClientError) as err:
        srv.route(make_app(), "GET", "/clock/start", AUTH)
    assert err.value.status == HTTPStatus.METHOD_NOT_ALLOWED


@pytest.mark.parametrize("path", ["/plan", "/clock"])
def test_read_endpoints_require_get(path):
    with pytest.raises(srv.ClientError) as err:
        srv.route(make_app(), "POST", path, AUTH)
    assert err.value.status == HTTPStatus.METHOD_NOT_ALLOWED


def test_health_answers_while_clock_action_runs(live_server):
    import threading

    release = threading.Event()
    app = make_app()
    app = srv.App(app.token, app.plan_for, lambda action: release.wait(5) and {}, app.today)
    base = live_server(app)
    worker = threading.Thread(target=_request, args=(f"{base}/clock/stop", "POST"))
    worker.start()
    try:
        assert _request(f"{base}/health", auth=None)[0] == 200
    finally:
        release.set()
        worker.join()


def test_unknown_action_and_path_are_404():
    for path in ("/clock/explode", "/nope"):
        with pytest.raises(srv.ClientError) as err:
            srv.route(make_app(), "POST", path, AUTH)
        assert err.value.status == HTTPStatus.NOT_FOUND


@pytest.mark.parametrize(
    "env,message",
    [
        ({"TB_API_TOKEN": "short"}, "TB_API_TOKEN"),
        ({"TB_API_TOKEN": TOKEN}, "TIMEBUTLER_USERNAME"),
    ],
)
def test_build_app_fails_fast_on_missing_settings(env, message):
    with pytest.raises(SystemExit, match=message):
        srv.build_app(env)


@pytest.fixture
def live_server():
    def start(app):
        server = ThreadingHTTPServer(("127.0.0.1", 0), srv.make_handler(app))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}"

    servers = []
    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def _request(url, method="GET", auth=AUTH):
    req = urllib.request.Request(url, method=method, headers={"Authorization": auth} if auth else {})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_http_roundtrip_success_envelope(live_server):
    base = live_server(make_app())
    status, body = _request(f"{base}/clock/start", "POST")
    assert status == 200
    assert body == {"success": True, "data": {"action": "start"}, "error": None}


def test_http_unauthorized_envelope(live_server):
    base = live_server(make_app())
    status, body = _request(f"{base}/plan", auth=None)
    assert status == 401
    assert body["success"] is False


def test_http_internal_error_hides_details(live_server):
    base = live_server(make_app(clock_error=RuntimeError("secret detail")))
    status, body = _request(f"{base}/clock/stop", "POST")
    assert status == 500
    assert body["success"] is False
    assert "secret" not in body["error"]
