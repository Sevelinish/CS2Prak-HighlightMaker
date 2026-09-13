from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from rich.console import Console

from .theme import supports_text

DONE_MARK = "✓"
FAILED_MARK = "✗"
ASCII_DONE_MARK = "OK"
ASCII_FAILED_MARK = "!!"
DETAIL_INDENT = "      "


class StepReporter:
    def __init__(self, console: Console, total: int) -> None:
        self._console = console
        self._total = total
        self._started = 0
        self._open = False
        unicode_safe = supports_text(console, DONE_MARK + FAILED_MARK)
        self._done_mark = DONE_MARK if unicode_safe else ASCII_DONE_MARK
        self._failed_mark = FAILED_MARK if unicode_safe else ASCII_FAILED_MARK

    def begin(self, title: str) -> None:
        self._started += 1
        self._open = True
        self._console.print(
            f"[accent]{self._started}/{self._total}[/accent] [brand]{title}[/brand]"
        )

    def detail(self, message: str) -> None:
        self._console.print(f"{DETAIL_INDENT}[muted]{message}[/muted]")

    def done(self, note: str = "") -> None:
        if not self._open:
            return
        self._open = False
        suffix = f" [muted]{note}[/muted]" if note else ""
        self._console.print(f"{DETAIL_INDENT}[success]{self._done_mark}[/success]{suffix}")

    def fail(self, note: str = "") -> None:
        if not self._open:
            return
        self._open = False
        suffix = f" {note}" if note else " failed"
        self._console.print(f"{DETAIL_INDENT}[danger]{self._failed_mark}{suffix}[/danger]")

    @contextmanager
    def step(self, title: str) -> Iterator["StepReporter"]:
        self.begin(title)
        try:
            yield self
        except BaseException:
            self.fail()
            raise
        self.done()
