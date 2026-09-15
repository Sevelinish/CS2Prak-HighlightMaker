from __future__ import annotations

from ..config.repository import ConfigRepository
from ..game.installation import Cs2Installation
from ..infrastructure.errors import GameNotFoundError, HighlighterError
from ..infrastructure.logging import LoggingConfigurator
from ..infrastructure.paths import ApplicationPaths
from ..presentation.banner import Banner
from ..presentation.import_view import SKIP_WORD, STOP_WORD, ImportView
from ..presentation.theme import build_console
from .importer import DemoImporter

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
SUBTITLE = "bringing new demos into the demo folder"


class DemoGetCommand:
    def __init__(self, verbose: bool = False) -> None:
        self._paths = ApplicationPaths.discover()
        self._console = build_console()
        self._view = ImportView(self._console)
        self._logger = LoggingConfigurator(self._paths.logs, verbose).configure()

    def run(self) -> int:
        self._console.print(Banner.build(SUBTITLE))
        try:
            return self._execute()
        except HighlighterError as error:
            self._console.print(f"[danger]{error}[/danger]")
            self._logger.debug("Import aborted", exc_info=True)
            return EXIT_FAILURE
        except KeyboardInterrupt:
            self._console.print("\n[warning]Cancelled[/warning]")
            return EXIT_FAILURE

    def _execute(self) -> int:
        config = ConfigRepository(self._paths.config_file).load()
        importer = DemoImporter(self._paths, config, self._installation(config))

        self._console.print()
        self._view.searched(importer.searched_directories())
        self._console.print()

        candidates = importer.candidates()
        if not candidates:
            self._view.nothing_new()
            return EXIT_SUCCESS

        self._view.found(candidates)
        imported = self._walk(importer, candidates)
        importer.cleanup()
        self._view.finished(imported, importer.demo_directory)
        return EXIT_SUCCESS

    def _walk(self, importer: DemoImporter, candidates: list) -> int:
        imported = 0
        for position, demo in enumerate(candidates, start=1):
            self._view.unpacking(demo, position, len(candidates))
            try:
                candidate = importer.prepare(demo)
            except HighlighterError as error:
                self._view.failed(str(error))
                continue

            self._view.describe(candidate)
            answer = self._view.ask_name(candidate)

            if answer.lower() == STOP_WORD:
                importer.discard(candidate)
                break
            if not answer or answer.lower() == SKIP_WORD:
                importer.skip(candidate)
                self._view.skipped()
                continue

            try:
                self._view.stored(importer.store(candidate, answer))
                imported += 1
            except HighlighterError as error:
                importer.discard(candidate)
                self._view.failed(str(error))
        return imported

    def _installation(self, config) -> Cs2Installation | None:
        try:
            return Cs2Installation.discover(config.paths.cs2_directory)
        except GameNotFoundError:
            self._logger.debug("CS2 was not found, only looking in Downloads")
            return None
