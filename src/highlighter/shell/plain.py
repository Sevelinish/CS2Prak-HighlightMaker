from __future__ import annotations

from rich.console import Console


class PlainPrompt:
    def __init__(self, console: Console, prompt: str) -> None:
        self._console = console
        self._prompt = prompt

    def read(self) -> str | None:
        try:
            return self._console.input(f"[accent]{self._prompt}[/accent]")
        except (EOFError, KeyboardInterrupt):
            self._console.print()
            return None
