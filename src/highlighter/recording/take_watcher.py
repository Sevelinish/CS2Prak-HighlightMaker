from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..infrastructure.logging import get_logger
from ..plan.models import RecordingPlan

VIDEO_SUFFIXES = (".mp4", ".mkv", ".mov", ".avi")
DEFAULT_POLL_INTERVAL_SECONDS = 1.0


@dataclass(frozen=True, slots=True)
class TakeProgress:
    completed: int
    total: int
    bytes_written: int
    elapsed_seconds: float = 0.0

    @property
    def is_complete(self) -> bool:
        return self.total > 0 and self.completed >= self.total

    @property
    def has_started(self) -> bool:
        return self.bytes_written > 0

    def same_shape_as(self, other: "TakeProgress") -> bool:
        return (
            self.completed == other.completed
            and self.bytes_written == other.bytes_written
        )


class TakeWatcher:
    def __init__(
        self,
        plan: RecordingPlan,
        take_directory: Path,
        settle_seconds: float,
        stall_seconds: float,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> None:
        self._roots = [
            take_directory / clip.name / segment.name
            for clip in plan.clips
            for segment in clip.segments
        ]
        self._settle_seconds = settle_seconds
        self._stall_seconds = stall_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._logger = get_logger("recording.takes")

    @property
    def segment_count(self) -> int:
        return len(self._roots)

    def snapshot(self, elapsed_seconds: float = 0.0) -> TakeProgress:
        completed = 0
        written = 0
        for root in self._roots:
            size = self._recorded_bytes(root)
            written += size
            if size > 0:
                completed += 1
        return TakeProgress(
            completed=completed,
            total=len(self._roots),
            bytes_written=written,
            elapsed_seconds=elapsed_seconds,
        )

    def wait_for_start(
        self,
        timeout_seconds: float,
        is_alive: Callable[[], bool] | None = None,
    ) -> bool:
        started_at = time.monotonic()
        while time.monotonic() - started_at < timeout_seconds:
            if self.snapshot().has_started:
                return True
            if is_alive is not None and not is_alive():
                return False
            time.sleep(self._poll_interval_seconds)
        return self.snapshot().has_started

    def settle(self, timeout_seconds: float) -> TakeProgress:
        started_at = time.monotonic()
        settled_since = 0.0
        previous = self.snapshot()

        while True:
            elapsed = time.monotonic() - started_at
            if elapsed >= timeout_seconds:
                self._logger.warning(
                    "Takes were still being written after %.0fs", elapsed
                )
                return self.snapshot(elapsed)

            time.sleep(self._poll_interval_seconds)
            current = self.snapshot(time.monotonic() - started_at)
            if current.same_shape_as(previous):
                settled_since += self._poll_interval_seconds
            else:
                settled_since = 0.0
            previous = current

            if settled_since >= self._settle_seconds:
                self._logger.debug(
                    "Takes settled after %.1fs at %d byte(s)",
                    current.elapsed_seconds,
                    current.bytes_written,
                )
                return current

    def wait(
        self,
        timeout_seconds: float,
        on_started: Callable[[], None] | None = None,
        on_progress: Callable[[TakeProgress], None] | None = None,
        is_alive: Callable[[], bool] | None = None,
    ) -> TakeProgress:
        started_at = time.monotonic()
        announced = False
        settled_since = 0.0
        previous = self.snapshot()

        while True:
            elapsed = time.monotonic() - started_at
            current = self.snapshot(elapsed)

            if not announced and current.has_started:
                announced = True
                if on_started is not None:
                    on_started()

            if current.has_started and current.same_shape_as(previous):
                settled_since += self._poll_interval_seconds
            else:
                settled_since = 0.0
            previous = current

            if current.is_complete and settled_since >= self._settle_seconds:
                self._logger.debug("All %d take(s) settled", current.total)
                return current

            if is_alive is not None and not is_alive():
                self._logger.debug("Game is gone, letting the takes finish writing")
                return self.settle(self._stall_seconds)

            if current.has_started and settled_since >= self._stall_seconds:
                self._logger.warning(
                    "Takes stopped changing at %d of %d segment(s)",
                    current.completed,
                    current.total,
                )
                return current

            if elapsed >= timeout_seconds:
                self._logger.warning("Take watch timed out after %.0fs", elapsed)
                return current

            if on_progress is not None:
                on_progress(current)
            time.sleep(self._poll_interval_seconds)

    @staticmethod
    def _recorded_bytes(root: Path) -> int:
        if not root.is_dir():
            return 0
        total = 0
        for candidate in root.rglob("*"):
            if candidate.is_file() and candidate.suffix.lower() in VIDEO_SUFFIXES:
                try:
                    total += candidate.stat().st_size
                except OSError:
                    continue
        return total
