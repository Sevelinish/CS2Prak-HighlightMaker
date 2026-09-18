from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from rich.console import Console
from rich.table import Table

from ..library import DemoProfile

NAME_WIDTH = 36
ProfileLookup = Callable[[Path], "DemoProfile | None"]


class DemoPicker:
    def __init__(self, console: Console, profile_for: ProfileLookup | None = None) -> None:
        self._console = console
        self._profile_for = profile_for or (lambda demo: None)

    def pick(self, demos: list[Path]) -> Path | None:
        if not demos:
            return None
        if len(demos) == 1:
            return demos[0]

        self._render(demos)
        while True:
            try:
                raw = self._console.input("[accent]> [/accent]").strip()
            except (EOFError, KeyboardInterrupt):
                self._console.print()
                return None

            if not raw or raw.lower() in {"q", "quit", "none"}:
                return None
            if raw.isdigit() and 1 <= int(raw) <= len(demos):
                return demos[int(raw) - 1]
            self._console.print("[danger]Enter a number from the table[/danger]")

    def _render(self, demos: list[Path]) -> None:
        table = Table(
            title="[brand]Available demos[/brand]",
            title_justify="left",
            header_style="accent",
            border_style="muted",
        )
        table.add_column("#", justify="right", width=3)
        table.add_column("Demo", overflow="ellipsis", no_wrap=True, max_width=NAME_WIDTH)
        table.add_column("Map", no_wrap=True)
        table.add_column("Players", justify="right", width=7)
        table.add_column("Modified", justify="right", width=16)

        for index, demo in enumerate(demos, start=1):
            profile = self._profile_for(demo)
            table.add_row(
                str(index),
                demo.name,
                profile.map_name if profile is not None else "",
                str(len(profile.players)) if profile is not None else "",
                datetime.fromtimestamp(demo.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            )

        self._console.print(table)
        self._console.print("[muted]Pick a demo by number, or [/muted][brand]q[/brand][muted] to quit[/muted]")
