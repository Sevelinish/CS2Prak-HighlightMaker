from __future__ import annotations

import csv
import io
import subprocess
import time
from typing import Callable

from ..infrastructure.logging import get_logger

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
IMAGE_NAME_COLUMN = 0
PROCESS_ID_COLUMN = 1
DEFAULT_POLL_INTERVAL_SECONDS = 1.0


class GameProcessWatcher:
    def __init__(
        self,
        executable_name: str,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> None:
        self._executable_name = executable_name
        self._poll_interval_seconds = poll_interval_seconds
        self._logger = get_logger("recording.process")

    @property
    def executable_name(self) -> str:
        return self._executable_name

    def running_process_ids(self) -> list[int]:
        completed = subprocess.run(
            [
                "tasklist",
                "/FI",
                f"IMAGENAME eq {self._executable_name}",
                "/NH",
                "/FO",
                "CSV",
            ],
            capture_output=True,
            text=True,
            errors="replace",
            creationflags=NO_WINDOW,
        )

        process_ids: list[int] = []
        for row in csv.reader(io.StringIO(completed.stdout)):
            if len(row) <= PROCESS_ID_COLUMN:
                continue
            if row[IMAGE_NAME_COLUMN].lower() != self._executable_name.lower():
                continue
            try:
                process_ids.append(int(row[PROCESS_ID_COLUMN]))
            except ValueError:
                continue
        return process_ids

    def is_running(self) -> bool:
        return bool(self.running_process_ids())

    def wait_until_started(self, timeout_seconds: float) -> bool:
        return self._poll_until(lambda: self.is_running(), timeout_seconds)

    def wait_until_stopped(
        self,
        timeout_seconds: float,
        on_poll: Callable[[float], None] | None = None,
    ) -> bool:
        return self._poll_until(lambda: not self.is_running(), timeout_seconds, on_poll)

    def terminate(self) -> None:
        for process_id in self.running_process_ids():
            self._logger.warning("Terminating %s (pid %d)", self._executable_name, process_id)
            subprocess.run(
                ["taskkill", "/F", "/PID", str(process_id)],
                capture_output=True,
                creationflags=NO_WINDOW,
            )

    def _poll_until(
        self,
        predicate: Callable[[], bool],
        timeout_seconds: float,
        on_poll: Callable[[float], None] | None = None,
    ) -> bool:
        started_at = time.monotonic()
        while True:
            if predicate():
                return True

            elapsed = time.monotonic() - started_at
            if elapsed >= timeout_seconds:
                return False
            if on_poll is not None:
                on_poll(elapsed)
            time.sleep(self._poll_interval_seconds)
