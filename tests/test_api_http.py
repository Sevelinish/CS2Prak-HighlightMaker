from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from highlighter.api.dispatcher import CommandDispatcher
from highlighter.api.errors import ApiError, ErrorCode
from highlighter.api.events import EventJournal, EventType
from highlighter.api.transport.http import HttpApiServer

TOKEN = "test-token"


class ServiceDouble:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def __getattr__(self, name):
        def handler(payload):
            self.calls.append((name, dict(payload)))
            if payload.get("explode"):
                raise ApiError(ErrorCode.DEMO_NOT_FOUND, "no such demo")
            return {"command": name, "payload": dict(payload)}

        return handler


@pytest.fixture
def api():
    journal = EventJournal()
    service = ServiceDouble()
    server = HttpApiServer(
        dispatcher=CommandDispatcher(service),
        journal=journal,
        host="127.0.0.1",
        port=0,
        token=TOKEN,
    )
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield server, service, journal
    finally:
        server.stop_signal.set()
        worker.join(timeout=5)


def call(server, path, payload=None, token=TOKEN, method="POST"):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(server.base_url + path, data=data, method=method)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def test_the_server_binds_to_loopback_only(api):
    server, _, _ = api

    assert server.host == "127.0.0.1"
    assert server.port > 0


def test_health_needs_no_token(api):
    server, _, _ = api
    status, body = call(server, "/health", method="GET", token="")

    assert status == 200
    assert body["status"] == "ok"
    assert body["protocol"]


def test_a_command_runs_through_the_envelope_route(api):
    server, service, _ = api
    status, body = call(server, "/v1/command", {"command": "demos.list", "payload": {"limit": 3}})

    assert status == 200
    assert body["ok"] is True
    assert body["data"]["payload"] == {"limit": 3}
    assert service.calls[-1][0] == "demos_list"


def test_a_command_runs_through_its_own_route(api):
    server, _, _ = api
    status, body = call(server, "/v1/highlights.find", {"demo": "a.dem"})

    assert status == 200
    assert body["data"]["payload"] == {"demo": "a.dem"}


def test_the_client_identifier_comes_back_unchanged(api):
    server, _, _ = api
    _, body = call(server, "/v1/command", {"id": "abc-123", "command": "config.get"})

    assert body["id"] == "abc-123"


def test_a_missing_token_is_refused(api):
    server, _, _ = api
    status, body = call(server, "/v1/config.get", {}, token="")

    assert status == 401
    assert body["error"]["code"] == "unauthorized"


def test_a_wrong_token_is_refused(api):
    server, _, _ = api
    status, _ = call(server, "/v1/config.get", {}, token="nope")

    assert status == 401


def test_an_unknown_route_is_a_not_found(api):
    server, _, _ = api
    status, body = call(server, "/v2/whatever", {})

    assert status == 404
    assert body["error"]["code"] == "unknown_command"


def test_an_unknown_command_lists_the_available_ones(api):
    server, _, _ = api
    status, body = call(server, "/v1/command", {"command": "does.not.exist"})

    assert status == 404
    assert "handshake" in body["error"]["details"]["available"]


def test_malformed_json_is_a_bad_request(api):
    server, _, _ = api
    request = urllib.request.Request(
        server.base_url + "/v1/command", data=b"{not json", method="POST"
    )
    request.add_header("Authorization", f"Bearer {TOKEN}")
    with pytest.raises(urllib.error.HTTPError) as raised:
        urllib.request.urlopen(request, timeout=10)

    assert raised.value.code == 400


def test_a_domain_error_keeps_its_http_status(api):
    server, _, _ = api
    status, body = call(server, "/v1/demos.inspect", {"explode": True})

    assert status == 404
    assert body["error"]["code"] == "demo_not_found"


def test_a_preflight_is_answered_for_a_loopback_origin(api):
    server, _, _ = api
    request = urllib.request.Request(server.base_url + "/v1/command", method="OPTIONS")
    request.add_header("Origin", "http://127.0.0.1:5000")
    with urllib.request.urlopen(request, timeout=10) as response:
        allowed = response.headers.get("Access-Control-Allow-Origin")
        methods = response.headers.get("Access-Control-Allow-Methods")

    assert allowed == "http://127.0.0.1:5000"
    assert "POST" in methods


def test_an_outside_origin_gets_no_cors_grant(api):
    server, _, _ = api
    request = urllib.request.Request(server.base_url + "/v1/command", method="OPTIONS")
    request.add_header("Origin", "https://example.com")
    with urllib.request.urlopen(request, timeout=10) as response:
        assert response.headers.get("Access-Control-Allow-Origin") is None


def test_events_are_readable_over_http(api):
    server, _, journal = api
    journal.publish("job-x", EventType.JOB_STARTED, {"a": 1})
    status, body = call(server, "/v1/events?since=0", method="GET")

    assert status == 200
    assert body["data"]["payload"]["since"] == "0"


def test_the_event_stream_sends_newline_delimited_json(api):
    server, _, journal = api
    request = urllib.request.Request(server.base_url + "/v1/events/stream?since=0")
    request.add_header("Authorization", f"Bearer {TOKEN}")
    journal.publish("job-y", EventType.JOB_STARTED, {"a": 1})

    with urllib.request.urlopen(request, timeout=10) as response:
        assert response.headers.get("Content-Type").startswith("application/x-ndjson")
        line = response.readline().decode("utf-8").strip()

    payload = json.loads(line)
    assert payload["kind"] == "event"
    assert payload["jobId"] == "job-y"
