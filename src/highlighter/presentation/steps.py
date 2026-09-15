from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from rich.console import Console

from .theme import supports_text

DONE_MARK = "[+]"
FAILED_MARK = "[-]"
DETAIL_MARK = "·"
ASCII_DETAIL_MARK = "-"
MARK_WIDTH = 3
GUTTER = "       "
SECONDS_PER_MINUTE = 60


class Duration:
    @staticmethod
    def render(seconds: float) -> str:
        if seconds < 10:
            return f"{seconds:.1f}s"
        if seconds < SECONDS_PER_MINUTE:
            return f"{seconds:.0f}s"
        minutes, remainder = divmod(int(seconds), SECONDS_PER_MINUTE)
        return f"{minutes}m {remainder:02d}s"


class StepReporter:
    def __init__(self, console: Console, total: int) -> None:
        self._console = console
        self._total = total
        self._started = 0
        self._open = False
        self._started_at = 0.0
        self._detail_mark = self._centered(
            DETAIL_MARK if supports_text(console, DETAIL_MARK) else ASCII_DETAIL_MARK
        )

    def begin(self, title: str) -> None:
        self._started += 1
        self._open = True
        self._started_at = time.monotonic()
        counter = f"{self._started}/{self._total}"
        self._console.print(f"[accent]{counter:>5}[/accent]  [brand]{title}[/brand]")

    def detail(self, message: str) -> None:
        self._console.print(f"{GUTTER}[muted]{self._detail_mark} {message}[/muted]")

    def done(self, note: str = "") -> None:
        if not self._open:
            return
        self._open = False
        body = f" {note} " if note else " "
        self._console.print(
            f"{GUTTER}[success]{DONE_MARK}[/success]{body} {self._elapsed()}"
        )

    def fail(self, note: str = "") -> None:
        if not self._open:
            return
        self._open = False
        body = note or "failed"
        self._console.print(
            f"{GUTTER}[danger]{FAILED_MARK} {body}[/danger]  {self._elapsed()}"
        )

    def _elapsed(self) -> str:
        return f"[muted]{Duration.render(time.monotonic() - self._started_at)}[/muted]"

    @staticmethod
    def _centered(mark: str) -> str:
        return f"{mark:^{MARK_WIDTH}}"

    @contextmanager
    def step(self, title: str) -> Iterator["StepReporter"]:
        self.begin(title)
        try:
            yield self
        except BaseException:
            self.fail()
            raise
        self.done()
