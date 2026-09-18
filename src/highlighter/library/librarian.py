from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ..infrastructure.logging import get_logger
from .index import DemoIndex
from .inspector import DemoProfiler
from .profile import DemoProfile

DEFAULT_BUDGET_SECONDS = 25.0
UNLIMITED = 0.0


@dataclass(frozen=True, slots=True)
class IndexingReport:
    read: int = 0
    left: int = 0
    players: int = 0
    seconds: float = 0.0

    @property
    def did_work(self) -> bool:
        return self.read > 0

    @property
    def ran_out_of_time(self) -> bool:
        return self.left > 0


class DemoLibrarian:
    def __init__(
        self,
        index: DemoIndex,
        profiler: DemoProfiler | None = None,
        budget_seconds: float = DEFAULT_BUDGET_SECONDS,
    ) -> None:
        self._index = index
        self._profiler = profiler or DemoProfiler()
        self._budget = budget_seconds
        self._logger = get_logger("library")

    def unknown(self, demos: Sequence[Path]) -> list[Path]:
        return [demo for demo in demos if not self._index.knows(demo)]

    def catch_up(
        self, demos: Sequence[Path], budget_seconds: float | None = None
    ) -> IndexingReport:
        pending = self.unknown(demos)
        if not pending:
            return IndexingReport()

        budget = self._budget if budget_seconds is None else budget_seconds
        started = time.monotonic()
        read = 0
        players = 0

        for position, demo in enumerate(pending):
            if self._out_of_time(started, budget, position):
                break
            profile = self._profiler.profile(demo)
            self._index.remember(profile)
            read += 1
            players += len(profile.players)

        return IndexingReport(
            read=read,
            left=len(pending) - read,
            players=players,
            seconds=time.monotonic() - started,
        )

    def remember(self, profile: DemoProfile) -> None:
        self._index.remember(profile)

    @staticmethod
    def _out_of_time(started: float, budget: float, position: int) -> bool:
        if budget <= UNLIMITED or position == 0:
            return False
        return time.monotonic() - started >= budget
