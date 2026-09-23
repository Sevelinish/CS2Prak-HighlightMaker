from __future__ import annotations

from rich.console import Console

from ..config.repository import ConfigRepository
from ..infrastructure.errors import HighlighterError
from ..infrastructure.logging import get_logger
from ..infrastructure.paths import ApplicationPaths
from .check import ToolchainInspector
from .report import ToolsView

LOOKING_MESSAGE = "Asking the release pages what the newest builds are"


class ToolsCommand:
    def __init__(
        self, console: Console, paths: ApplicationPaths | None = None
    ) -> None:
        self._console = console
        self._paths = paths or ApplicationPaths.discover()
        self._logger = get_logger("tooling")

    def run(self, ask_online: bool = True) -> int:
        try:
            checks = self._inspect(ask_online)
        except HighlighterError as error:
            self._console.print(f"[danger]{error}[/danger]")
            return 1

        ToolsView(self._console).render(checks)
        return 0

    def _inspect(self, ask_online: bool):
        config = ConfigRepository(self._paths.config_file).load()
        inspector = ToolchainInspector(
            paths=config.paths,
            settings=config.toolchain,
            tools_directory=self._paths.resolve(config.paths.tools_directory),
            hook_dll_relative_path=config.game.hook_dll_relative_path,
            application_paths=self._paths,
        )
        if ask_online:
            self._console.print(f"[muted]{LOOKING_MESSAGE}[/muted]")
        return inspector.inspect(ask_online)
