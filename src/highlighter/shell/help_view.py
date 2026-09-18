from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

from rich.console import Console
from rich.table import Table

from ..library import DemoProfile, PlayerHint
from ..version import __version__
from .grammar import Grammar

EXAMPLES = (
    ("mirage17.dem -p s1mple", "that demo, only that player"),
    ("mirage17.dem -enemy -one-file", "add the victim view, join it all into one file"),
    ("mirage17.dem -m nades_smoke -fly", "every smoke, filmed from behind the grenade"),
    ("-demoget", "import new demos from Downloads and the game folders"),
)

KEYS = (
    ("Tab", "take the grey suggestion, press again to see the next match"),
    ("Right, End", "take the grey suggestion"),
    ("Up, Down", "walk through what you typed before"),
    ("Ctrl+C", "clear the line, or leave when the line is empty"),
)

DEMO_COLUMN_WIDTH = 40


class HelpView:
    def __init__(self, console: Console, grammar: Grammar | None = None) -> None:
        self._console = console
        self._grammar = grammar or Grammar()

    def render(self) -> None:
        self._console.print()
        self._console.print(
            "[brand]Type the arguments you would pass to the exe, one run per line.[/brand]"
        )
        self._render_flags()
        self._render_commands()
        self._render_keys()
        self._render_examples()
        self._console.print()

    def _render_flags(self) -> None:
        table = self._table("Arguments")
        for option in self._grammar.options:
            table.add_row(self._flag_label(option), option.summary)
        self._console.print(table)

    def _render_commands(self) -> None:
        table = self._table("Words the prompt understands on its own")
        for command in self._grammar.commands:
            table.add_row(", ".join(command.names), command.summary)
        self._console.print(table)

    def _render_keys(self) -> None:
        table = self._table("Keys")
        for key, summary in KEYS:
            table.add_row(key, summary)
        self._console.print(table)

    def _render_examples(self) -> None:
        table = self._table("Examples")
        for line, summary in EXAMPLES:
            table.add_row(line, summary)
        self._console.print(table)

    def _table(self, title: str) -> Table:
        table = Table(
            title=f"[accent]{title}[/accent]",
            title_justify="left",
            show_header=False,
            box=None,
            padding=(0, 2, 0, 0),
        )
        table.add_column(style="brand", no_wrap=True)
        table.add_column(style="muted")
        return table

    @staticmethod
    def _flag_label(option) -> str:
        label = option.primary
        if option.takes_value:
            label = f"{label} {option.placeholder}"
        return label


class VersionView:
    def __init__(self, console: Console) -> None:
        self._console = console

    def render(self) -> None:
        self._console.print(f"[brand]HighlighterCS2[/brand] [muted]{__version__}[/muted]")


class DemoListView:
    def __init__(self, console: Console) -> None:
        self._console = console

    def render(
        self,
        demos: Sequence[Path],
        profile_for: Callable[[Path], DemoProfile | None] | None = None,
    ) -> None:
        if not demos:
            self._console.print("[warning]No demos found in the search folders[/warning]")
            return

        lookup = profile_for or (lambda demo: None)
        table = Table(
            title="[accent]Demos the prompt can complete[/accent]",
            title_justify="left",
            header_style="accent",
            box=None,
            padding=(0, 2, 0, 0),
        )
        table.add_column(
            "Demo",
            style="brand",
            no_wrap=True,
            max_width=DEMO_COLUMN_WIDTH,
            overflow="ellipsis",
        )
        table.add_column("Map", style="muted", no_wrap=True)
        table.add_column("Players", style="muted", justify="right")
        table.add_column("Folder", style="muted", no_wrap=True)

        self._console.print()
        for demo in demos:
            profile = lookup(demo)
            table.add_row(
                demo.name,
                profile.map_name if profile is not None else "",
                str(len(profile.players)) if profile is not None else "",
                demo.parent.name,
            )
        self._console.print(table)
        self._console.print()


class PlayerListView:
    def __init__(self, console: Console) -> None:
        self._console = console

    def render(self, players: Sequence[PlayerHint], demo_name: str = "") -> None:
        if not players:
            self._console.print(
                "[warning]No nicknames known yet, run [/warning]"
                "[brand]demos[/brand][warning] to read them[/warning]"
            )
            return

        scope = f" in {demo_name}" if demo_name else " across every demo read so far"
        table = Table(
            title=f"[accent]Players{scope}[/accent]",
            title_justify="left",
            show_header=False,
            box=None,
            padding=(0, 2, 0, 0),
        )
        table.add_column(style="brand", no_wrap=True)
        table.add_column(style="muted", no_wrap=True, overflow="ellipsis")
        table.add_column(style="muted", no_wrap=True)

        self._console.print()
        for hint in players:
            table.add_row(hint.name, hint.note, str(hint.steam_id64 or ""))
        self._console.print(table)
        self._console.print(
            "[muted]Type one after [/muted][brand]-p[/brand][muted], "
            "or press Tab there to walk through them[/muted]"
        )
        self._console.print()
