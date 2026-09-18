from __future__ import annotations

import argparse
from dataclasses import dataclass

from rich.console import Console

from ..cli import CommandLine, CommandLineError, CommandLineStop
from ..entrypoint import EntryPoint
from ..infrastructure.errors import HighlighterError
from ..infrastructure.logging import get_logger
from ..update.command import UpdateCommand
from .catalogue import DemoCatalogue

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_BAD_ARGUMENTS = 2


@dataclass(frozen=True, slots=True)
class ShellResult:
    exit_code: int = EXIT_SUCCESS
    should_exit: bool = False


class ShellRunner:
    def __init__(self, console: Console, catalogue: DemoCatalogue | None = None) -> None:
        self._console = console
        self._catalogue = catalogue
        self._logger = get_logger("shell")

    def run(self, argv: list[str]) -> ShellResult:
        try:
            arguments = CommandLine.parse_quietly(argv)
        except CommandLineError as error:
            self._console.print(f"[danger]{error}[/danger]")
            self._console.print("[muted]type help to see what is accepted[/muted]")
            return ShellResult(exit_code=EXIT_BAD_ARGUMENTS)
        except CommandLineStop:
            return ShellResult()

        return self._execute(arguments)

    def _execute(self, arguments: argparse.Namespace) -> ShellResult:
        self._console.print()
        if arguments.update:
            return self._update(arguments)
        try:
            code = EntryPoint.execute(arguments, show_banner=False)
        except HighlighterError as error:
            self._console.print(f"[danger]{error}[/danger]")
            return ShellResult(exit_code=EXIT_FAILURE)
        except KeyboardInterrupt:
            self._console.print("\n[warning]Cancelled[/warning]")
            return ShellResult(exit_code=EXIT_FAILURE)
        except Exception as error:
            self._logger.exception("A command failed inside the prompt")
            self._console.print(f"[danger]{type(error).__name__}: {error}[/danger]")
            self._console.print("[muted]the details are in logs/highlighter.log[/muted]")
            return ShellResult(exit_code=EXIT_FAILURE)

        self._refresh_after(arguments)
        self._console.print()
        return ShellResult(exit_code=code)

    def _update(self, arguments: argparse.Namespace) -> ShellResult:
        command = UpdateCommand(verbose=arguments.verbose)
        code = command.run()
        if command.staged:
            self._console.print("[muted]closing the prompt so the files can be swapped[/muted]")
        return ShellResult(exit_code=code, should_exit=command.staged)

    def _refresh_after(self, arguments: argparse.Namespace) -> None:
        if self._catalogue is not None and arguments.demo_get:
            self._catalogue.refresh()
