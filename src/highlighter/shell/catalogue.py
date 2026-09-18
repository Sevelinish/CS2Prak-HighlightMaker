from __future__ import annotations

import time
from pathlib import Path

from ..config.repository import ConfigRepository
from ..config.schema import ApplicationConfig
from ..demo.locator import DemoLocator
from ..game.installation import Cs2Installation
from ..infrastructure.logging import get_logger
from ..infrastructure.paths import ApplicationPaths
from ..library import DemoLibrary, DemoProfile, IndexingReport, PlayerHint

REFRESH_SECONDS = 20.0
IMMEDIATE = 0.0


class DemoCatalogue:
    def __init__(
        self, paths: ApplicationPaths | None = None, library: DemoLibrary | None = None
    ) -> None:
        self._paths = paths or ApplicationPaths.discover()
        self._logger = get_logger("shell")
        self._library = library
        self._config: ApplicationConfig | None = None
        self._demos: tuple[Path, ...] = ()
        self._read_at = 0.0

    def names(self) -> tuple[str, ...]:
        return tuple(demo.name for demo in self.demos())

    def demos(self) -> tuple[Path, ...]:
        if time.monotonic() - self._read_at < REFRESH_SECONDS:
            return self._demos
        self._demos = self._discover()
        self._read_at = time.monotonic()
        return self._demos

    def refresh(self) -> None:
        self._read_at = 0.0

    def profiles(self) -> tuple[DemoProfile, ...]:
        library = self.library()
        return library.profiles() if library is not None else ()

    def profile_for(self, demo: Path) -> DemoProfile | None:
        library = self.library()
        return library.profile_for(demo) if library is not None else None

    def players(self, demo_name: str = "") -> tuple[PlayerHint, ...]:
        library = self.library()
        if library is None:
            return ()
        if demo_name:
            self._index_named(library, demo_name)
        return library.players(demo_name)

    def catch_up(self, budget_seconds: float | None = None) -> IndexingReport:
        library = self.library()
        if library is None:
            return IndexingReport()
        return library.catch_up(self.demos(), budget_seconds)

    def forget_missing(self) -> int:
        library = self.library()
        return library.forget_missing(self.demos()) if library is not None else 0

    def waiting(self) -> int:
        library = self.library()
        return len(library.unknown(self.demos())) if library is not None else 0

    def library(self) -> DemoLibrary | None:
        if self._library is None:
            self._library = self._build_library()
        return self._library

    def _build_library(self) -> DemoLibrary | None:
        config = self._configuration()
        if config is None:
            return None
        try:
            return DemoLibrary(self._paths.resolve(config.paths.work_directory))
        except OSError:
            self._logger.debug("The demo index is unavailable", exc_info=True)
            return None

    def _index_named(self, library: DemoLibrary, demo_name: str) -> None:
        if library.named(demo_name) is not None:
            return
        found = self._demo_called(demo_name)
        if found is None:
            return
        library.catch_up([found], budget_seconds=IMMEDIATE)

    def _demo_called(self, demo_name: str) -> Path | None:
        wanted = demo_name.strip().lower()
        for demo in self.demos():
            if wanted in {demo.name.lower(), demo.stem.lower()}:
                return demo
        return None

    def _discover(self) -> tuple[Path, ...]:
        try:
            return tuple(DemoLocator(self._directories()).discover())
        except Exception:
            self._logger.debug("Demo suggestions unavailable", exc_info=True)
            return ()

    def _directories(self) -> list[Path]:
        config = self._configuration()
        if config is None:
            return []
        directories = [self._paths.resolve(config.paths.demo_directory)]
        try:
            directories.extend(
                Cs2Installation.discover(config.paths.cs2_directory).demo_directories()
            )
        except Exception:
            self._logger.debug("CS2 demo folders unavailable", exc_info=True)
        return directories

    def _configuration(self) -> ApplicationConfig | None:
        if self._config is not None:
            return self._config
        try:
            self._config = ConfigRepository(self._paths.config_file).load()
        except Exception:
            self._logger.debug("config.json could not be read for the prompt", exc_info=True)
            return None
        return self._config
