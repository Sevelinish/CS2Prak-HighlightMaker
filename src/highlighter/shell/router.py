from __future__ import annotations

from rich.console import Console

from .catalogue import DemoCatalogue
from .grammar import Grammar
from .help_view import DemoListView, HelpView, PlayerListView, VersionView
from .reading import NO_BUDGET, NewDemoReader
from .renderer import LineRenderer
from .runner import ShellResult, ShellRunner
from .tokens import Lexer

RUN_COMMAND = "run"
HELP_COMMAND = "help"
DEMOS_COMMAND = "demos"
PLAYERS_COMMAND = "players"
CLEAR_COMMAND = "clear"
VERSION_COMMAND = "version"
EXIT_COMMAND = "exit"


class CommandRouter:
    def __init__(
        self,
        console: Console,
        runner: ShellRunner,
        catalogue: DemoCatalogue,
        renderer: LineRenderer | None = None,
        grammar: Grammar | None = None,
    ) -> None:
        self._console = console
        self._runner = runner
        self._catalogue = catalogue
        self._renderer = renderer
        self._grammar = grammar or Grammar()

    def route(self, line: str) -> ShellResult:
        argv = Lexer.argv(line)
        if not argv:
            return ShellResult()

        command = self._grammar.command_for(argv[0])
        if command is None:
            return self._runner.run(argv)

        handler = getattr(self, f"_on_{command.primary}")
        return handler(argv[1:])

    def _on_run(self, argv: list[str]) -> ShellResult:
        return self._runner.run(argv)

    def _on_help(self, argv: list[str]) -> ShellResult:
        HelpView(self._console, self._grammar).render()
        return ShellResult()

    def _on_demos(self, argv: list[str]) -> ShellResult:
        self._catalogue.refresh()
        self._forget_missing()
        NewDemoReader(self._console, self._catalogue).read(NO_BUDGET)
        DemoListView(self._console).render(
            self._catalogue.demos(), self._catalogue.profile_for
        )
        return ShellResult()

    def _on_players(self, argv: list[str]) -> ShellResult:
        demo_name = argv[0] if argv else ""
        PlayerListView(self._console).render(
            self._catalogue.players(demo_name), demo_name
        )
        return ShellResult()

    def _forget_missing(self) -> None:
        dropped = self._catalogue.forget_missing()
        if dropped:
            self._console.print(
                f"[muted]{dropped} demo(s) are gone from the folders, "
                f"dropped from the book[/muted]"
            )

    def _on_clear(self, argv: list[str]) -> ShellResult:
        if self._renderer is not None:
            self._renderer.clear_screen()
        else:
            self._console.clear()
        return ShellResult()

    def _on_version(self, argv: list[str]) -> ShellResult:
        VersionView(self._console).render()
        return ShellResult()

    def _on_exit(self, argv: list[str]) -> ShellResult:
        return ShellResult(should_exit=True)
