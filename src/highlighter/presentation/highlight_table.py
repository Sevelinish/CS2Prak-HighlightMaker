from __future__ import annotations

from rich.console import Console
from rich.table import Table

from ..domain.highlight import Highlight
from ..domain.match import Match
from .theme import score_style


class HighlightTable:
    def __init__(self, console: Console, match: Match) -> None:
        self._console = console
        self._match = match

    def render(self, highlights: list[Highlight]) -> None:
        table = Table(
            title=f"[brand]{self._match.demo_name}[/brand]  [muted]{self._match.map_name}[/muted]",
            title_justify="left",
            header_style="accent",
            border_style="muted",
            expand=False,
        )
        table.add_column("#", justify="right", width=3)
        table.add_column("Round", justify="right", width=5)
        table.add_column("Player", overflow="ellipsis", max_width=18)
        table.add_column("Side", justify="center", width=4)
        table.add_column("K", justify="right", width=2)
        table.add_column("HS", justify="right", width=2)
        table.add_column("Length", justify="right", width=7)
        table.add_column("Score", justify="right", width=6)
        table.add_column("Highlights", overflow="fold")

        for index, highlight in enumerate(highlights, start=1):
            table.add_row(
                str(index),
                str(highlight.round_number),
                highlight.player.name,
                self._side_cell(highlight),
                str(highlight.kill_count),
                str(highlight.headshot_count),
                self._length_cell(highlight),
                f"[{score_style(highlight.score)}]{highlight.score:g}[/]",
                highlight.headline,
            )

        self._console.print(table)

    @staticmethod
    def _side_cell(highlight: Highlight) -> str:
        if highlight.side is None:
            return "[muted]?[/muted]"
        style = "side.t" if highlight.side.label == "T" else "side.ct"
        return f"[{style}]{highlight.side.label}[/{style}]"

    def _length_cell(self, highlight: Highlight) -> str:
        span = self._match.ticks_to_seconds(highlight.last_tick - highlight.first_tick)
        return f"{span:.1f}s"
