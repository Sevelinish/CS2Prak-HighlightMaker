from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ..domain.match import Match
from .directory import PlayerDirectory, PlayerHint
from .index import DemoIndex
from .inspector import DemoProfiler
from .librarian import DemoLibrarian, IndexingReport
from .profile import DemoProfile


class DemoLibrary:
    def __init__(
        self,
        work_directory: Path,
        librarian: DemoLibrarian | None = None,
        profiler: DemoProfiler | None = None,
    ) -> None:
        self._index = DemoIndex(work_directory)
        self._profiler = profiler or DemoProfiler()
        self._librarian = librarian or DemoLibrarian(self._index, self._profiler)

    @property
    def index_file(self) -> Path:
        return self._index.file

    @property
    def known_count(self) -> int:
        return self._index.count

    def profiles(self) -> tuple[DemoProfile, ...]:
        return self._index.profiles()

    def profile_for(self, demo: Path) -> DemoProfile | None:
        return self._index.profile_for(demo)

    def named(self, demo_name: str) -> DemoProfile | None:
        return self._index.named(demo_name)

    def unknown(self, demos: Sequence[Path]) -> list[Path]:
        return self._librarian.unknown(demos)

    def forget_missing(self, demos: Sequence[Path]) -> int:
        return self._index.keep_only(demos)

    def catch_up(
        self, demos: Sequence[Path], budget_seconds: float | None = None
    ) -> IndexingReport:
        return self._librarian.catch_up(demos, budget_seconds)

    def remember_match(self, match: Match) -> DemoProfile:
        profile = self._profiler.from_match(match)
        self._librarian.remember(profile)
        return profile

    def players(self, demo_name: str = "") -> tuple[PlayerHint, ...]:
        return PlayerDirectory(self.profiles()).hints(demo_name)

    def player_count(self) -> int:
        return len(PlayerDirectory(self.profiles()).hints())
