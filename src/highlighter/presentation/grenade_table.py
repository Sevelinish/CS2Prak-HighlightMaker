from __future__ import annotations

from rich.console import Console
from rich.table import Table

from ..domain.grenade import Grenade
from ..domain.match import Match


class GrenadeTable:
    def __init__(self, console: Console, match: Match) -> None:
        self._console = console
        self._match = match

    def render(self, grenades: list[Grenade]) -> None:
        table = Table(
            title=f"[brand]{self._match.demo_name}[/brand]  [muted]{self._match.map_name}[/muted]",
            title_justify="left",
            header_style="accent",
            border_style="muted",
        )
        table.add_column("#", justify="right", width=3)
        table.add_column("Rnd", justify="right", width=3)
        table.add_column("Time", justify="right", width=5)
        table.add_column("Player", overflow="ellipsis", max_width=16)
        table.add_column("Side", justify="center", width=4)
        table.add_column("Kind", width=7)
        table.add_column("Landed", overflow="ellipsis", max_width=18)
        table.add_column("Flight", justify="right", width=6)
        table.add_column("Position / Angles", overflow="fold", max_width=30)

        for index, grenade in enumerate(grenades, start=1):
            table.add_row(
                str(index),
                str(grenade.round_number),
                grenade.round_clock,
                grenade.thrower.name,
                self._side_cell(grenade),
                grenade.kind.label,
                grenade.landing_place,
                f"{self._match.ticks_to_seconds(grenade.flight_ticks):.1f}s",
                self._placement_cell(grenade),
            )

        self._console.print(table)

    @staticmethod
    def _placement_cell(grenade: Grenade) -> str:
        position = grenade.thrower_position
        angles = grenade.thrower_angles
        return (
            f"{position.x:.0f} {position.y:.0f} {position.z:.0f}"
            f" [muted]|[/muted] {angles.pitch:.1f} {angles.yaw:.1f}"
        )

    @staticmethod
    def _side_cell(grenade: Grenade) -> str:
        if grenade.side is None:
            return "[muted]?[/muted]"
        style = "side.t" if grenade.side.label == "T" else "side.ct"
        return f"[{style}]{grenade.side.label}[/{style}]"
