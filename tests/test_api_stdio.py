from __future__ import annotations

import io
import json
import threading
import time

from highlighter.api.dispatcher import CommandDispatcher
from highlighter.api.events import EventJournal, EventType
from highlighter.api.transport.stdio import StdioTransport

WAIT_SECONDS = 5.0


class ServiceDouble:
    def __getattr__(self, name):
        return lambda payload: {"command": name, "payload": dict(payload)}


def run(lines: list[dict], stream_events: bool = False) -> list[dict]:
    source = io.StringIO("\n".join(json.dumps(line) for line in lines) + "\n")
    sink = io.StringIO()
    StdioTransport(
        CommandDispatcher(ServiceDouble()),
        EventJournal(),
        stream_events=stream_events,
        source=source,
        sink=sink,
    ).serve()
    return [json.loads(line) for line in sink.getvalue().splitlines() if line.strip()]


def test_one_request_per_line_gets_one_response_per_line():
    answers = run([{"command": "handshake"}, {"command": "demos.list"}])

    assert [answer["command"] for answer in answers] == ["handshake", "demos.list"]
    assert all(answer["kind"] == "response" for answer in answers)


def test_the_payload_reaches_the_service():
    answers = run([{"command": "highlights.find", "payload": {"demo": "a.dem"}}])

    assert answers[0]["data"]["payload"] == {"demo": "a.dem"}


def test_the_client_identifier_comes_back_unchanged():
    answers = run([{"id": "req-9", "command": "config.get"}])

    assert answers[0]["id"] == "req-9"


def test_a_malformed_line_does_not_kill_the_session():
    source = io.StringIO('{"command": "handshake"}\nnot json\n{"command": "config.get"}\n')
    sink = io.StringIO()
    StdioTransport(
        CommandDispatcher(ServiceDouble()),
        EventJournal(),
        stream_events=False,
        source=source,
        sink=sink,
    ).serve()
    answers = [json.loads(line) for line in sink.getvalue().splitlines() if line.strip()]

    assert len(answers) == 3
    assert answers[1]["ok"] is False
    assert answers[1]["error"]["code"] == "bad_request"
    assert answers[2]["ok"] is True


def test_a_request_without_a_command_is_a_bad_request():
    answers = run([{"payload": {}}])

    assert answers[0]["error"]["code"] == "bad_request"


def test_blank_lines_are_ignored():
    source = io.StringIO('\n\n{"command": "handshake"}\n\n')
    sink = io.StringIO()
    StdioTransport(
        CommandDispatcher(ServiceDouble()),
        EventJournal(),
        stream_events=False,
        source=source,
        sink=sink,
    ).serve()

    assert len(sink.getvalue().strip().splitlines()) == 1


def test_events_are_pushed_alongside_responses():
    journal = EventJournal()
    source = _BlockingSource('{"command": "handshake"}\n')
    sink = io.StringIO()
    transport = StdioTransport(
        CommandDispatcher(ServiceDouble()),
        journal,
        stream_events=True,
        source=source,
        sink=sink,
    )
    worker = threading.Thread(target=transport.serve, daemon=True)
    worker.start()

    journal.publish("job-1", EventType.JOB_STARTED, {"a": 1})
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline and "event" not in sink.getvalue():
        time.sleep(0.05)
    source.close()
    worker.join(timeout=WAIT_SECONDS)

    kinds = [
        json.loads(line)["kind"] for line in sink.getvalue().splitlines() if line.strip()
    ]
    assert "event" in kinds
    assert "response" in kinds


class _BlockingSource:
    def __init__(self, text: str) -> None:
        self._lines = text.splitlines(keepends=True)
        self._closed = threading.Event()

    def __iter__(self):
        for line in self._lines:
            yield line
        self._closed.wait(WAIT_SECONDS)

    def close(self) -> None:
        self._closed.set()
