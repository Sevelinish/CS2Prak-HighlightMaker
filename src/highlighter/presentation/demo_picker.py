from __future__ import annotations

from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

BYTES_PER_MEGABYTE = 1024 * 1024


class DemoPicker:
    def __init__(self, console: Console) -> None:
        self._console = console

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
        table.add_column("Demo", overflow="ellipsis", max_width=52)
        table.add_column("Size", justify="right", width=9)
        table.add_column("Modified", justify="right", width=16)

        for index, demo in enumerate(demos, start=1):
            stats = demo.stat()
            table.add_row(
                str(index),
                demo.name,
                f"{stats.st_size / BYTES_PER_MEGABYTE:.1f} MB",
                datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M"),
            )

        self._console.print(table)
        self._console.print("[muted]Pick a demo by number, or [/muted][brand]q[/brand][muted] to quit[/muted]")
