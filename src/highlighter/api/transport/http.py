from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse

from ...infrastructure.logging import get_logger
from ..contract import (
    AUTHORIZATION_HEADER,
    PLUGIN_NAME,
    PLUGIN_VERSION,
    PROTOCOL_VERSION,
    TOKEN_SCHEME,
)
from ..dispatcher import CommandDispatcher
from ..envelope import ApiRequest, ApiResponse
from ..errors import ApiError, ErrorCode, ErrorTranslator
from ..events import EventJournal

TRANSPORT_NAME = "http"
HEALTH_PATH = "/health"
COMMAND_PATH = "/v1/command"
COMMAND_PREFIX = "/v1/"
HANDSHAKE_PATH = "/v1/handshake"
EVENTS_PATH = "/v1/events"
EVENTS_STREAM_PATH = "/v1/events/stream"
JSON_CONTENT_TYPE = "application/json; charset=utf-8"
NDJSON_CONTENT_TYPE = "application/x-ndjson; charset=utf-8"
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "[::1]")
MAXIMUM_BODY_BYTES = 4 * 1024 * 1024
STREAM_POLL_SECONDS = 1.0


class HttpApiServer:
    def __init__(
        self,
        dispatcher: CommandDispatcher,
        journal: EventJournal,
        host: str,
        port: int,
        token: str,
        stop: threading.Event | None = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._journal = journal
        self._token = token
        self._stop = stop or threading.Event()
        self._logger = get_logger("api.http")
        self._server = ThreadingHTTPServer((host, port), self._handler_class())
        self._server.daemon_threads = True

    @property
    def host(self) -> str:
        return self._server.server_address[0]

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def serve_forever(self) -> None:
        worker = threading.Thread(target=self._server.serve_forever, daemon=True)
        worker.start()
        try:
            while not self._stop.wait(timeout=0.25):
                continue
        finally:
            self.close()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _handler_class(self):
        server = self

        class Handler(ApiRequestHandler):
            api = server

        return Handler

    @property
    def dispatcher(self) -> CommandDispatcher:
        return self._dispatcher

    @property
    def journal(self) -> EventJournal:
        return self._journal

    @property
    def token(self) -> str:
        return self._token

    @property
    def stop_signal(self) -> threading.Event:
        return self._stop


class ApiRequestHandler(BaseHTTPRequestHandler):
    api: HttpApiServer
    protocol_version = "HTTP/1.1"
    server_version = f"{PLUGIN_NAME}/{PLUGIN_VERSION}"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:
        self.api._logger.debug("%s %s", self.address_string(), format % args)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        route = urlparse(self.path)
        query = parse_qs(route.query)

        if route.path == HEALTH_PATH:
            self._send_json(HTTPStatus.OK, self._health())
            return
        if not self._authorized():
            return
        if route.path == HANDSHAKE_PATH:
            self._dispatch(ApiRequest.create("handshake", self._flatten(query)))
            return
        if route.path == EVENTS_STREAM_PATH:
            self._stream_events(query)
            return
        if route.path == EVENTS_PATH:
            self._dispatch(ApiRequest.create("jobs.events", self._flatten(query)))
            return
        self._send_error_body(HTTPStatus.NOT_FOUND, ErrorCode.UNKNOWN_COMMAND, "Unknown route")

    def do_POST(self) -> None:
        route = urlparse(self.path)
        if not self._authorized():
            return

        body = self._read_body()
        if body is None:
            return

        if route.path == COMMAND_PATH:
            try:
                request = ApiRequest.from_mapping(body)
            except BaseException as error:
                self._send_response(ApiResponse.failed(None, ErrorTranslator.translate(error)))
                return
            self._dispatch(request)
            return

        if route.path.startswith(COMMAND_PREFIX):
            command = route.path[len(COMMAND_PREFIX) :].strip("/")
            payload = body if isinstance(body, Mapping) else {}
            self._dispatch(ApiRequest.create(command, payload))
            return

        self._send_error_body(HTTPStatus.NOT_FOUND, ErrorCode.UNKNOWN_COMMAND, "Unknown route")

    def _health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "plugin": PLUGIN_NAME,
            "version": PLUGIN_VERSION,
            "protocol": PROTOCOL_VERSION,
        }

    def _dispatch(self, request: ApiRequest) -> None:
        self._send_response(self.api.dispatcher.handle(request))

    def _stream_events(self, query: Mapping[str, list[str]]) -> None:
        cursor = int(self._single(query, "since", "0") or 0)
        job_id = self._single(query, "jobId", "")

        self.send_response(HTTPStatus.OK)
        self._send_cors()
        self.send_header("Content-Type", NDJSON_CONTENT_TYPE)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        try:
            while not self.api.stop_signal.is_set():
                page = self.api.journal.read(
                    since=cursor,
                    job_id=job_id or None,
                    wait_seconds=STREAM_POLL_SECONDS,
                )
                for event in page.events:
                    self._write_chunk(json.dumps(event.to_mapping(), ensure_ascii=False) + "\n")
                cursor = max(cursor, page.next_sequence)
                if not page.events:
                    self._write_chunk("\n")
            self._write_chunk("")
        except (BrokenPipeError, ConnectionResetError, OSError):
            self.close_connection = True

    def _write_chunk(self, text: str) -> None:
        payload = text.encode("utf-8")
        self.wfile.write(f"{len(payload):X}\r\n".encode("ascii"))
        self.wfile.write(payload + b"\r\n")
        self.wfile.flush()

    def _authorized(self) -> bool:
        if not self.api.token:
            return True
        header = self.headers.get(AUTHORIZATION_HEADER, "")
        expected = f"{TOKEN_SCHEME} {self.api.token}"
        if header.strip() == expected:
            return True
        self._send_error_body(
            HTTPStatus.UNAUTHORIZED,
            ErrorCode.UNAUTHORIZED,
            f"Send the API token as '{AUTHORIZATION_HEADER}: {TOKEN_SCHEME} <token>'",
        )
        return False

    def _read_body(self) -> Any:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        if length > MAXIMUM_BODY_BYTES:
            self._send_error_body(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                ErrorCode.BAD_REQUEST,
                "The request body is too large",
            )
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            self._send_error_body(
                HTTPStatus.BAD_REQUEST, ErrorCode.BAD_REQUEST, f"Malformed JSON: {error}"
            )
            return None

    def _send_response(self, response: ApiResponse) -> None:
        status = HTTPStatus.OK if response.ok else self._status_for(response.error)
        self._send_json(status, response.to_mapping())

    def _send_error_body(self, status: HTTPStatus, code: ErrorCode, message: str) -> None:
        self._send_json(
            status, ApiResponse.failed(None, ApiError(code, message)).to_mapping()
        )

    def _send_json(self, status: HTTPStatus, payload: Mapping[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self._send_cors()
        self.send_header("Content-Type", JSON_CONTENT_TYPE)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _send_cors(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin and self._is_loopback(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header(
                "Access-Control-Allow-Headers", f"{AUTHORIZATION_HEADER}, Content-Type"
            )

    @staticmethod
    def _is_loopback(origin: str) -> bool:
        host = urlparse(origin).hostname or ""
        return host in {"127.0.0.1", "localhost", "::1"}

    @staticmethod
    def _status_for(error: ApiError | None) -> HTTPStatus:
        if error is None:
            return HTTPStatus.INTERNAL_SERVER_ERROR
        return _STATUS_BY_CODE.get(error.code, HTTPStatus.BAD_REQUEST)

    @staticmethod
    def _single(query: Mapping[str, list[str]], key: str, fallback: str = "") -> str:
        values = query.get(key) or []
        return values[0] if values else fallback

    @classmethod
    def _flatten(cls, query: Mapping[str, list[str]]) -> dict[str, Any]:
        return {key: values[0] for key, values in query.items() if values}


_STATUS_BY_CODE = {
    ErrorCode.UNAUTHORIZED: HTTPStatus.UNAUTHORIZED,
    ErrorCode.UNKNOWN_COMMAND: HTTPStatus.NOT_FOUND,
    ErrorCode.DEMO_NOT_FOUND: HTTPStatus.NOT_FOUND,
    ErrorCode.JOB_NOT_FOUND: HTTPStatus.NOT_FOUND,
    ErrorCode.EMPTY_SELECTION: HTTPStatus.CONFLICT,
    ErrorCode.JOB_CONFLICT: HTTPStatus.CONFLICT,
    ErrorCode.GAME_NOT_FOUND: HTTPStatus.FAILED_DEPENDENCY,
    ErrorCode.TOOLCHAIN_UNAVAILABLE: HTTPStatus.FAILED_DEPENDENCY,
    ErrorCode.DOWNLOAD_FAILED: HTTPStatus.BAD_GATEWAY,
    ErrorCode.RECORDING_FAILED: HTTPStatus.INTERNAL_SERVER_ERROR,
    ErrorCode.ENCODING_FAILED: HTTPStatus.INTERNAL_SERVER_ERROR,
    ErrorCode.DEMO_UNREADABLE: HTTPStatus.UNPROCESSABLE_ENTITY,
    ErrorCode.CONFIG_INVALID: HTTPStatus.UNPROCESSABLE_ENTITY,
    ErrorCode.UNSUPPORTED_PROTOCOL: HTTPStatus.UPGRADE_REQUIRED,
    ErrorCode.CANCELLED: HTTPStatus.OK,
    ErrorCode.INTERNAL: HTTPStatus.INTERNAL_SERVER_ERROR,
}
