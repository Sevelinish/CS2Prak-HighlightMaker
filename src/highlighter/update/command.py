from __future__ import annotations

from ..config.repository import ConfigRepository
from ..infrastructure.errors import HighlighterError
from ..infrastructure.logging import LoggingConfigurator
from ..infrastructure.paths import ApplicationPaths
from ..presentation.theme import build_console
from .service import UpdateService

EXIT_SUCCESS = 0
EXIT_FAILURE = 1


class UpdateCommand:
    def __init__(self, verbose: bool = False) -> None:
        self._paths = ApplicationPaths.discover()
        self._console = build_console()
        self._logger = LoggingConfigurator(self._paths.logs, verbose).configure()

    def run(self) -> int:
        try:
            config = ConfigRepository(self._paths.config_file).load()
            service = UpdateService(self._console, self._paths, config)
            service.announce_installed()
            return EXIT_SUCCESS if service.run() else EXIT_FAILURE
        except HighlighterError as error:
            self._console.print(f"[danger]{error}[/danger]")
            self._logger.debug("Update aborted", exc_info=True)
            return EXIT_FAILURE
        except KeyboardInterrupt:
            self._console.print("\n[warning]Cancelled[/warning]")
            return EXIT_FAILURE
