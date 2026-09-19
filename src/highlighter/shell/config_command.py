from __future__ import annotations

from pathlib import Path

from rich.console import Console

from ..editor import ConfigEditor
from ..infrastructure.errors import HighlighterError
from ..infrastructure.logging import get_logger

STRAY_PREVIEW_LIMIT = 6


class ConfigCommand:
    def __init__(
        self, console: Console, config_file: Path, editing: bool = True
    ) -> None:
        self._console = console
        self._config_file = config_file
        self._editing = editing
        self._logger = get_logger("shell")

    def run(self) -> None:
        if not self._editing:
            self._point_elsewhere()
            return
        try:
            self._open()
        except HighlighterError as error:
            self._console.print(f"[danger]{error}[/danger]")
        except OSError as error:
            self._console.print(f"[danger]config.json could not be opened: {error}[/danger]")

    def _open(self) -> None:
        outcome = ConfigEditor(self._config_file).run()
        if not outcome.saved:
            self._console.print("[muted]config.json was left as it was[/muted]")
            return

        self._console.print(f"[success]config.json saved[/success] [muted]{self._config_file}[/muted]")
        self._console.print("[muted]the next run picks it up[/muted]")
        self._warn_about(outcome.dropped_keys)

    def _warn_about(self, strays: tuple[str, ...]) -> None:
        if not strays:
            return
        shown = ", ".join(strays[:STRAY_PREVIEW_LIMIT])
        if len(strays) > STRAY_PREVIEW_LIMIT:
            shown += ", ..."
        self._console.print(
            f"[warning]{len(strays)} setting(s) are not part of the schema "
            f"and the next run will drop them: {shown}[/warning]"
        )

    def _point_elsewhere(self) -> None:
        self._console.print(
            "[warning]This console cannot host the editor[/warning]"
        )
        self._console.print(f"[muted]Edit it yourself: {self._config_file}[/muted]")
