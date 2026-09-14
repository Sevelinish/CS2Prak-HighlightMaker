from __future__ import annotations

import json
import os
import secrets
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config.repository import ConfigRepository
from ..infrastructure.logging import LoggingConfigurator, get_logger
from ..infrastructure.paths import ApplicationPaths
from .contract import (
    DEFAULT_HTTP_HOST,
    DEFAULT_HTTP_PORT,
    PLUGIN_NAME,
    PLUGIN_VERSION,
    PROTOCOL_VERSION,
)
from .dispatcher import CommandDispatcher
from .service import PluginService
from .transport.http import TRANSPORT_NAME as HTTP_TRANSPORT, HttpApiServer
from .transport.stdio import TRANSPORT_NAME as STDIO_TRANSPORT, StdioTransport
from .workspace import DemoWorkspace

TOKEN_BYTES = 24
EXIT_SUCCESS = 0
EXIT_FAILURE = 1


@dataclass(frozen=True, slots=True)
class ApiOptions:
    transport: str = HTTP_TRANSPORT
    host: str = DEFAULT_HTTP_HOST
    port: int = DEFAULT_HTTP_PORT
    token: str = ""
    endpoint_file: str = ""
    stream_events: bool = True
    verbose: bool = False

    @property
    def is_stdio(self) -> bool:
        return self.transport == STDIO_TRANSPORT


class ApiRuntime:
    def __init__(self, options: ApiOptions) -> None:
        self._options = options
        self._paths = ApplicationPaths.discover()
        self._logger = LoggingConfigurator(
            self._paths.logs, options.verbose, console=not options.is_stdio
        ).configure()
        self._repository = ConfigRepository(self._paths.config_file)
        config = self._repository.load()
        self._workspace = DemoWorkspace(self._paths, config)
        self._service = PluginService(
            self._workspace, self._repository, transports=(options.transport,)
        )
        self._dispatcher = CommandDispatcher(self._service)

    @property
    def service(self) -> PluginService:
        return self._service

    @property
    def dispatcher(self) -> CommandDispatcher:
        return self._dispatcher

    def run(self) -> int:
        self._service.start()
        try:
            if self._options.is_stdio:
                return self._serve_stdio()
            return self._serve_http()
        finally:
            self._service.stop()

    def _serve_stdio(self) -> int:
        self._announce({"transport": STDIO_TRANSPORT})
        transport = StdioTransport(
            self._dispatcher,
            self._service.journal,
            stream_events=self._options.stream_events,
        )
        return transport.serve(self._service.shutdown_requested)

    def _serve_http(self) -> int:
        token = self._options.token or secrets.token_urlsafe(TOKEN_BYTES)
        server = HttpApiServer(
            dispatcher=self._dispatcher,
            journal=self._service.journal,
            host=self._options.host,
            port=self._options.port,
            token=token,
            stop=self._service.shutdown_requested,
        )
        endpoint = {
            "transport": HTTP_TRANSPORT,
            "baseUrl": server.base_url,
            "host": server.host,
            "port": server.port,
            "token": token,
        }
        self._announce(endpoint)
        self._write_endpoint_file(endpoint)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.close()
        return EXIT_SUCCESS

    def _announce(self, endpoint: dict[str, Any]) -> None:
        payload = {
            "kind": "ready",
            "plugin": PLUGIN_NAME,
            "version": PLUGIN_VERSION,
            "protocol": PROTOCOL_VERSION,
            "pid": os.getpid(),
            "root": str(self._paths.root),
            "configFile": str(self._repository.config_file),
            **endpoint,
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        self._logger.debug("API ready: %s", payload)

    def _write_endpoint_file(self, endpoint: dict[str, Any]) -> None:
        if not self._options.endpoint_file:
            return
        destination = self._paths.resolve(self._options.endpoint_file)
        destination.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "plugin": PLUGIN_NAME,
            "version": PLUGIN_VERSION,
            "protocol": PROTOCOL_VERSION,
            "pid": os.getpid(),
            **endpoint,
        }
        destination.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        self._logger.debug("Endpoint written to %s", destination)
