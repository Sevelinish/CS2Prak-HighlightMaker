from __future__ import annotations

from pathlib import Path

from rich.console import Console

from ..config.repository import ConfigRepository
from ..infrastructure.errors import HighlighterError
from ..infrastructure.logging import LoggingConfigurator
from ..infrastructure.paths import ApplicationPaths
from ..presentation.banner import Banner
from ..presentation.theme import build_console
from .catalogue import DemoCatalogue
from .history import HISTORY_FILE_NAME, CommandHistory
from .plain import PlainPrompt
from .prompt import LinePrompt
from .reading import NewDemoReader
from .reader import create_key_reader
from .renderer import LineRenderer
from .router import CommandRouter
from .runner import EXIT_SUCCESS, ShellRunner
from .suggester import Suggester
from .terminal import TerminalCapabilities

PROMPT = "> "
INTRO = (
    "[muted]Type a demo name and the flags you want. "
    "Suggestions appear in grey as you type.[/muted]"
)
GUIDE = (
    "[muted]Tab takes a suggestion, [/muted][brand]help[/brand][muted] shows everything, "
    "[/muted][brand]exit[/brand][muted] leaves.[/muted]"
)
PLAIN_NOTICE = (
    "[warning]This console does not support inline suggestions, "
    "the prompt still takes the same arguments[/warning]"
)


class ShellSession:
    def __init__(
        self, console: Console | None = None, paths: ApplicationPaths | None = None
    ) -> None:
        self._paths = paths or ApplicationPaths.discover()
        self._console = console or build_console()
        self._logger = LoggingConfigurator(self._paths.logs).configure()
        self._catalogue = DemoCatalogue(self._paths)
        self._history = CommandHistory(self._history_file())
        self._renderer = LineRenderer(PROMPT)
        self._editing = TerminalCapabilities.supports_line_editing()
        self._prompt = self._build_prompt()
        self._router = CommandRouter(
            console=self._console,
            runner=ShellRunner(self._console, self._catalogue),
            catalogue=self._catalogue,
            renderer=self._renderer,
        )

    def run(self) -> int:
        self._introduce()
        code = EXIT_SUCCESS
        while True:
            line = self._prompt.read()
            if line is None:
                break
            self._history.remember(line)
            result = self._router.route(line)
            code = result.exit_code
            if result.should_exit:
                break
        self._console.print()
        return code

    def _build_prompt(self) -> LinePrompt | PlainPrompt:
        if not self._editing:
            return PlainPrompt(self._console, PROMPT)
        return LinePrompt(
            reader=create_key_reader(),
            renderer=self._renderer,
            suggester=Suggester(
                demos=self._catalogue.names,
                history=self._history,
                players=self._catalogue.players,
            ),
            history=self._history,
        )

    def _introduce(self) -> None:
        self._console.print(Banner.build())
        if not self._editing:
            self._console.print(PLAIN_NOTICE)
        self._console.print(INTRO)
        self._console.print(GUIDE)
        self._console.print()
        if NewDemoReader(self._console, self._catalogue).read().did_work:
            self._console.print()

    def _history_file(self) -> Path | None:
        try:
            config = ConfigRepository(self._paths.config_file).load()
            work = self._paths.resolve(config.paths.work_directory)
        except (HighlighterError, OSError):
            self._logger.debug("Keeping the prompt history out of memory only")
            return None
        return work / HISTORY_FILE_NAME
