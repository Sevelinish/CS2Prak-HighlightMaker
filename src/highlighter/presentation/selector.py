from __future__ import annotations

from rich.console import Console

from ..domain.highlight import Highlight
from .selection_parser import SelectionParser

PROMPT_HINT = (
    "[muted]Enter clip numbers to record: [/muted]"
    "[brand]1,3,5-8[/brand][muted] | [/muted][brand]all[/brand][muted] | "
    "[/muted][brand]none[/brand][muted] to cancel[/muted]"
)


class HighlightSelector:
    def __init__(self, console: Console) -> None:
        self._console = console

    def select(self, highlights: list[Highlight]) -> list[Highlight]:
        if not highlights:
            return []

        parser = SelectionParser(len(highlights))
        while True:
            self._console.print(PROMPT_HINT)
            try:
                raw = self._console.input("[accent]> [/accent]")
            except (EOFError, KeyboardInterrupt):
                self._console.print()
                return []

            try:
                indexes = parser.parse(raw)
            except ValueError as error:
                self._console.print(f"[danger]{error}[/danger]")
                continue

            if not indexes:
                return []
            return [highlights[index - 1] for index in indexes]
