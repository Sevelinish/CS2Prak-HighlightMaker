from __future__ import annotations

import time
from pathlib import Path

from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from ..importing.archives import DemoFile
from ..importing.importer import ImportCandidate

BYTES_PER_MEGABYTE = 1024 * 1024
SKIP_WORD = "skip"
STOP_WORD = "stop"


class ImportView:
    def __init__(self, console: Console) -> None:
        self._console = console

    def searched(self, directories: list[Path]) -> None:
        self._console.print("[muted]Looked in:[/muted]")
        for directory in directories:
            self._console.print(f"  [muted]{directory}[/muted]")

    def nothing_new(self) -> None:
        self._console.print(
            Panel(
                "[success]No new demos[/success]\n"
                "[muted]everything in those folders has already been imported[/muted]",
                box=ROUNDED,
                border_style="muted",
                padding=(0, 2),
                expand=False,
            )
        )

    def found(self, demos: list[DemoFile]) -> None:
        table = Table(
            box=ROUNDED,
            border_style="muted",
            header_style="accent",
            title=f"[brand]{len(demos)} new demo(s)[/brand]",
            title_justify="left",
        )
        table.add_column("#", justify="right", width=3)
        table.add_column("File", overflow="fold")
        table.add_column("Size", justify="right", width=9)
        table.add_column("Downloaded", width=16)

        for index, demo in enumerate(demos, start=1):
            table.add_row(
                str(index),
                demo.path.name,
                f"{demo.size_bytes / BYTES_PER_MEGABYTE:.1f} MB",
                time.strftime("%Y-%m-%d %H:%M", time.localtime(demo.modified_at)),
            )
        self._console.print(table)

    def unpacking(self, demo: DemoFile, position: int, total: int) -> None:
        action = "Unpacking" if demo.is_archive else "Reading"
        self._console.print()
        counter = f"{position}/{total}"
        self._console.print(
            f"[accent]{counter:>5}[/accent]  [brand]{action} {demo.path.name}[/brand]"
        )

    def describe(self, candidate: ImportCandidate) -> None:
        summary = candidate.summary
        where = " [muted]from FACEIT[/muted]" if summary.is_faceit else ""
        size = f"{summary.size_bytes / BYTES_PER_MEGABYTE:.0f} MB"
        self._console.print(
            f"       [muted]·[/muted] {summary.map_name or 'unknown map'}{where}"
            f" [muted]{size}[/muted]"
        )

    def ask_name(self, candidate: ImportCandidate) -> str:
        suggestion = self._suggest(candidate)
        answer = Prompt.ask(
            f"       [brand]Name for this demo[/brand] "
            f"[muted]({SKIP_WORD} to pass, {STOP_WORD} to finish)[/muted]",
            default=suggestion,
            console=self._console,
        )
        return answer.strip()

    def stored(self, destination: Path) -> None:
        self._console.print(f"       [success][+][/success] {destination}")

    def skipped(self) -> None:
        self._console.print("       [muted][-] skipped[/muted]")

    def failed(self, reason: str) -> None:
        self._console.print(f"       [danger][-] {reason}[/danger]")

    def finished(self, imported: int, folder: Path) -> None:
        self._console.print()
        if not imported:
            self._console.print("[warning]Nothing was imported[/warning]")
            return
        self._console.print(
            Panel(
                f"[success]{imported} demo(s) ready[/success]\n[muted]{folder}[/muted]",
                box=ROUNDED,
                border_style="success",
                padding=(0, 2),
                expand=False,
            )
        )

    @staticmethod
    def _suggest(candidate: ImportCandidate) -> str:
        map_name = candidate.summary.map_name
        stamp = time.strftime("%d%m", time.localtime(candidate.source.modified_at))
        if map_name:
            return f"{map_name.removeprefix('de_')}{stamp}"
        return candidate.source.demo_name[:40]
