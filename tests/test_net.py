"""net.get() against a local HTTP server: retries, Retry-After, cancel, offline probe."""
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import requests

from src import net


class _Handler(BaseHTTPRequestHandler):
    script: list = []  # per-test list of (status, headers) responses, consumed in order
    hits = 0

    def do_GET(self):
        _Handler.hits += 1
        status, headers = (_Handler.script.pop(0) if _Handler.script else (200, {}))
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b"ok" if status == 200 else b"nope")

    def log_message(self, *args):
        pass


@pytest.fixture
def server(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _Handler.script = []
    _Handler.hits = 0
    monkeypatch.setattr(net, "RETRY_BACKOFF", 0.01)   # keep tests fast
    monkeypatch.setattr(net, "PROBE_URL", f"http://127.0.0.1:{srv.server_address[1]}/probe")
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_retries_then_succeeds(server):
    _Handler.script = [(503, {}), (503, {}), (200, {})]
    r = net.get(server + "/x", retries=3)
    assert r.status_code == 200 and _Handler.hits == 3


def test_gives_up_after_retries_and_returns_last_response(server):
    _Handler.script = [(503, {})] * 5
    r = net.get(server + "/x", retries=2)
    assert r.status_code == 503 and _Handler.hits == 3
    with pytest.raises(requests.HTTPError):
        r.raise_for_status()


def test_404_is_not_retried(server):
    _Handler.script = [(404, {})]
    r = net.get(server + "/x", retries=3)
    assert r.status_code == 404 and _Handler.hits == 1


def test_retry_after_header_is_honoured_and_capped(server, monkeypatch):
    monkeypatch.setattr(net, "RETRY_AFTER_MAX", 0.2)
    _Handler.script = [(429, {"Retry-After": "60"}), (200, {})]
    t = time.time()
    assert net.get(server + "/x", retries=1).status_code == 200
    assert 0.15 < time.time() - t < 2


def test_cancel_interrupts_backoff_wait(server, monkeypatch):
    monkeypatch.setattr(net, "RETRY_BACKOFF", 30)
    _Handler.script = [(503, {}), (200, {})]
    cancel = threading.Event()
    threading.Timer(0.2, cancel.set).start()
    t = time.time()
    with pytest.raises(net.Cancelled):
        net.get(server + "/x", retries=3, cancel=cancel)
    assert time.time() - t < 5


def test_cancel_already_set_raises_before_any_request(server):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(net.Cancelled):
        net.get(server + "/x", cancel=cancel)
    assert _Handler.hits == 0


def test_connection_error_with_internet_up_retries(server, monkeypatch):
    # Unreachable target, but the probe (local server) answers: not offline, so retries happen
    calls = {"n": 0}
    real_get = net.get_session().get

    def flaky(url, **kw):
        if "/probe" in url:
            return real_get(url, **kw)
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.ConnectionError("simulated")
        return real_get(server + "/x", **kw)

    monkeypatch.setattr(net.get_session(), "get", flaky)
    assert net.get("http://target/x", retries=3).status_code == 200
    assert calls["n"] == 3


def test_connection_error_with_internet_down_raises_offline_immediately(server, monkeypatch):
    calls = {"n": 0}

    def dead(url, **kw):
        calls["n"] += 1
        raise requests.ConnectionError("simulated: no network")

    monkeypatch.setattr(net.get_session(), "get", dead)
    with pytest.raises(net.Offline):
        net.get("http://target/x", retries=3)
    # one real attempt + one probe, no retries
    assert calls["n"] == 2


def test_offline_is_a_connection_error():
    assert issubclass(net.Offline, requests.ConnectionError)
