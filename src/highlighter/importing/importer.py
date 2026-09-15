from __future__ import annotations

import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from ..config.schema import ApplicationConfig
from ..game.installation import Cs2Installation
from ..infrastructure.errors import HighlighterError
from ..infrastructure.logging import get_logger
from ..infrastructure.paths import ApplicationPaths
from .archives import DEMO_SUFFIX, DemoExtractor, DemoFile
from .ledger import ImportLedger
from .sources import DemoSourceLocator

STAGING_DIRECTORY = "import"
FACEIT_MARKER = "faceit"
UNSAFE_NAME_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED_TRAILING = " ."
MAXIMUM_NAME_LENGTH = 80


@dataclass(frozen=True, slots=True)
class DemoSummary:
    map_name: str
    server_name: str = ""
    size_bytes: int = 0

    @property
    def is_faceit(self) -> bool:
        return FACEIT_MARKER in self.server_name.lower()


@dataclass(frozen=True, slots=True)
class ImportCandidate:
    source: DemoFile
    staged: Path
    summary: DemoSummary


class DemoInspector:
    def __init__(self) -> None:
        self._logger = get_logger("importing.inspect")

    def inspect(self, demo: Path) -> DemoSummary:
        size = demo.stat().st_size if demo.is_file() else 0
        try:
            from demoparser2 import DemoParser

            header = DemoParser(str(demo)).parse_header()
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as error:
            self._logger.warning("Could not read the header of %s: %s", demo.name, error)
            return DemoSummary(map_name="", size_bytes=size)

        return DemoSummary(
            map_name=str(header.get("map_name") or ""),
            server_name=str(header.get("server_name") or ""),
            size_bytes=size,
        )


class DemoImporter:
    def __init__(
        self,
        paths: ApplicationPaths,
        config: ApplicationConfig,
        installation: Cs2Installation | None,
    ) -> None:
        self._paths = paths
        self._config = config
        self._demos = paths.resolve(config.paths.demo_directory)
        self._staging = paths.resolve(config.paths.work_directory) / STAGING_DIRECTORY
        self._ledger = ImportLedger(paths.resolve(config.paths.work_directory))
        self._locator = DemoSourceLocator(installation)
        self._extractor = DemoExtractor()
        self._inspector = DemoInspector()
        self._logger = get_logger("importing")

    @property
    def demo_directory(self) -> Path:
        return self._demos

    @property
    def ledger(self) -> ImportLedger:
        return self._ledger

    def searched_directories(self) -> list[Path]:
        return self._locator.directories()

    def candidates(self) -> list[DemoFile]:
        return [demo for demo in self._locator.discover() if not self._ledger.knows(demo)]

    def prepare(self, demo: DemoFile) -> ImportCandidate:
        self._staging.mkdir(parents=True, exist_ok=True)
        staged = self._staging / f"{demo.demo_name}{DEMO_SUFFIX}"
        self._extractor.extract(demo, staged)
        return ImportCandidate(
            source=demo, staged=staged, summary=self._inspector.inspect(staged)
        )

    def store(self, candidate: ImportCandidate, wanted_name: str) -> Path:
        destination = self._destination(wanted_name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            candidate.staged.replace(destination)
        except OSError:
            shutil.move(str(candidate.staged), str(destination))

        self._ledger.remember(
            candidate.source, destination.name, candidate.summary.map_name, time.time()
        )
        self._logger.info("Imported %s as %s", candidate.source.path.name, destination.name)
        return destination

    def discard(self, candidate: ImportCandidate) -> None:
        candidate.staged.unlink(missing_ok=True)

    def skip(self, candidate: ImportCandidate) -> None:
        self.discard(candidate)
        self._ledger.remember(
            candidate.source, "", candidate.summary.map_name, time.time()
        )

    def cleanup(self) -> None:
        shutil.rmtree(self._staging, ignore_errors=True)

    def _destination(self, wanted_name: str) -> Path:
        stem = self.clean_name(wanted_name)
        if not stem:
            raise HighlighterError("A demo needs a name")

        candidate = self._demos / f"{stem}{DEMO_SUFFIX}"
        counter = 2
        while candidate.exists():
            candidate = self._demos / f"{stem}_{counter}{DEMO_SUFFIX}"
            counter += 1
        return candidate

    @staticmethod
    def clean_name(wanted: str) -> str:
        stem = wanted.strip()
        if stem.lower().endswith(DEMO_SUFFIX):
            stem = stem[: -len(DEMO_SUFFIX)]
        stem = UNSAFE_NAME_PATTERN.sub("_", stem).strip(RESERVED_TRAILING)
        return stem[:MAXIMUM_NAME_LENGTH]
