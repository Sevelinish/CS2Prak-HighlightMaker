from __future__ import annotations

import secrets
import socket
import time
from dataclasses import dataclass
from typing import Sequence

from ..infrastructure.logging import get_logger

LOOPBACK_HOST = "127.0.0.1"
PASSWORD_BYTES = 8
CONNECT_TIMEOUT_SECONDS = 2.0
PROBE_POLL_SECONDS = 0.5
LINE_TERMINATOR = "\n"
PASSWORD_COMMAND = "PASS"


@dataclass(frozen=True, slots=True)
class NetconEndpoint:
    port: int
    password: str = ""
    host: str = LOOPBACK_HOST

    @property
    def is_configured(self) -> bool:
        return self.port > 0

    @classmethod
    def create(cls, port: int = 0, password: str = "") -> "NetconEndpoint":
        return cls(
            port=port if port > 0 else free_port(),
            password=password or secrets.token_hex(PASSWORD_BYTES),
        )

    def launch_arguments(self) -> list[str]:
        if not self.is_configured:
            return []
        arguments = ["-netconport", str(self.port)]
        if self.password:
            arguments.extend(["-netconpassword", self.password])
        return arguments

    def to_mapping(self) -> dict[str, object]:
        return {"host": self.host, "port": self.port, "password": self.password}


class NetconClient:
    def __init__(
        self,
        endpoint: NetconEndpoint,
        timeout_seconds: float = CONNECT_TIMEOUT_SECONDS,
    ) -> None:
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds
        self._logger = get_logger("recording.netcon")

    @property
    def endpoint(self) -> NetconEndpoint:
        return self._endpoint

    def is_reachable(self) -> bool:
        if not self._endpoint.is_configured:
            return False
        try:
            with self._connect():
                return True
        except OSError:
            return False

    def wait_until_reachable(self, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while True:
            if self.is_reachable():
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(PROBE_POLL_SECONDS)

    def send(self, commands: Sequence[str]) -> bool:
        if not self._endpoint.is_configured or not commands:
            return False
        try:
            with self._connect() as connection:
                for command in commands:
                    connection.sendall((command + LINE_TERMINATOR).encode("utf-8"))
        except OSError as error:
            self._logger.debug("Netcon send failed: %s", error)
            return False
        self._logger.debug("Sent %d command(s) over netcon", len(commands))
        return True

    def _connect(self) -> socket.socket:
        connection = socket.create_connection(
            (self._endpoint.host, self._endpoint.port), timeout=self._timeout_seconds
        )
        if self._endpoint.password:
            connection.sendall(
                f"{PASSWORD_COMMAND} {self._endpoint.password}{LINE_TERMINATOR}".encode("utf-8")
            )
        return connection


def free_port(host: str = LOOPBACK_HOST) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((host, 0))
        return int(probe.getsockname()[1])
