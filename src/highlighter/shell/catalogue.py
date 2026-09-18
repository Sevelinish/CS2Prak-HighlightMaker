from __future__ import annotations

import time
from pathlib import Path

from ..config.repository import ConfigRepository
from ..demo.locator import DemoLocator
from ..game.installation import Cs2Installation
from ..infrastructure.logging import get_logger
from ..infrastructure.paths import ApplicationPaths

REFRESH_SECONDS = 20.0


class DemoCatalogue:
    def __init__(self, paths: ApplicationPaths | None = None) -> None:
        self._paths = paths or ApplicationPaths.discover()
        self._logger = get_logger("shell")
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

    def _discover(self) -> tuple[Path, ...]:
        try:
            return tuple(DemoLocator(self._directories()).discover())
        except Exception:
            self._logger.debug("Demo suggestions unavailable", exc_info=True)
            return ()

    def _directories(self) -> list[Path]:
        config = ConfigRepository(self._paths.config_file).load()
        directories = [self._paths.resolve(config.paths.demo_directory)]
        try:
            directories.extend(
                Cs2Installation.discover(config.paths.cs2_directory).demo_directories()
            )
        except Exception:
            self._logger.debug("CS2 demo folders unavailable", exc_info=True)
        return directories
