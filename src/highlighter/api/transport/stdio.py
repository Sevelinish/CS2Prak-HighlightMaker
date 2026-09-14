from __future__ import annotations

import json
import sys
import threading
from typing import Any, Mapping, TextIO

from ...infrastructure.logging import get_logger
from ..dispatcher import CommandDispatcher
from ..envelope import ApiRequest, ApiResponse
from ..errors import ApiError, ErrorCode, ErrorTranslator
from ..events import EventJournal

TRANSPORT_NAME = "stdio"
EVENT_POLL_SECONDS = 0.5


class NdjsonWriter:
    def __init__(self, stream: TextIO) -> None:
        self._stream = stream
        self._lock = threading.Lock()

    def write(self, payload: Mapping[str, Any]) -> None:
        line = json.dumps(payload, ensure_ascii=False, default=str)
        with self._lock:
            self._stream.write(line + "\n")
            self._stream.flush()


class EventPump:
    def __init__(self, journal: EventJournal, writer: NdjsonWriter) -> None:
        self._journal = journal
        self._writer = writer
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._pump, name="highlighter-events", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _pump(self) -> None:
        cursor = 0
        while not self._stopping.is_set():
            page = self._journal.read(since=cursor, wait_seconds=EVENT_POLL_SECONDS)
            for event in page.events:
                self._writer.write(event.to_mapping())
            cursor = max(cursor, page.next_sequence)


class StdioTransport:
    def __init__(
        self,
        dispatcher: CommandDispatcher,
        journal: EventJournal,
        stream_events: bool = True,
        source: TextIO | None = None,
        sink: TextIO | None = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._journal = journal
        self._stream_events = stream_events
        self._source = source or sys.stdin
        self._writer = NdjsonWriter(sink or sys.stdout)
        self._logger = get_logger("api.stdio")

    def serve(self, stop: threading.Event | None = None) -> int:
        pump = EventPump(self._journal, self._writer) if self._stream_events else None
        if pump is not None:
            pump.start()
        try:
            for line in self._source:
                if stop is not None and stop.is_set():
                    break
                text = line.strip()
                if not text:
                    continue
                self._writer.write(self._respond(text).to_mapping())
                if stop is not None and stop.is_set():
                    break
        finally:
            if pump is not None:
                pump.stop()
        return 0

    def _respond(self, text: str) -> ApiResponse:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as error:
            return ApiResponse.failed(
                None, ApiError(ErrorCode.BAD_REQUEST, f"Malformed JSON: {error.msg}")
            )
        try:
            request = ApiRequest.from_mapping(payload)
        except BaseException as error:
            return ApiResponse.failed(None, ErrorTranslator.translate(error))
        return self._dispatcher.handle(request)
