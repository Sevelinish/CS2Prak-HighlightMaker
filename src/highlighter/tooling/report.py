from __future__ import annotations

from typing import Sequence

from rich.console import Console
from rich.table import Table

from .check import ToolCheck, ToolState

UNKNOWN_MARK = "?"
STATE_STYLES = {
    ToolState.CURRENT: "success",
    ToolState.OUTDATED: "warning",
    ToolState.MISSING: "danger",
    ToolState.DAMAGED: "danger",
    ToolState.NEWER: "muted",
    ToolState.UNKNOWN: "muted",
}
PATH_WIDTH = 46


class ToolsView:
    def __init__(self, console: Console) -> None:
        self._console = console

    def render(self, checks: Sequence[ToolCheck]) -> None:
        self._console.print()
        self._console.print(self._versions(checks))
        self._console.print()
        self._console.print(self._places(checks))
        self._console.print()
        self._advise(checks)

    def _versions(self, checks: Sequence[ToolCheck]) -> Table:
        table = self._table("Tools")
        table.add_column("Tool", style="brand", no_wrap=True)
        table.add_column("Installed", no_wrap=True)
        table.add_column("Newest", no_wrap=True)
        table.add_column("", no_wrap=True)

        for check in checks:
            style = STATE_STYLES.get(check.state, "muted")
            table.add_row(
                check.status.label,
                check.status.shown_version or UNKNOWN_MARK,
                check.latest.shown or UNKNOWN_MARK,
                f"[{style}]{check.state.value}[/{style}]",
            )
        return table

    def _places(self, checks: Sequence[ToolCheck]) -> Table:
        table = self._table("Where they are")
        table.add_column("Tool", style="brand", no_wrap=True)
        table.add_column("Path", overflow="ellipsis", no_wrap=True, max_width=PATH_WIDTH)
        table.add_column("Found", no_wrap=True)

        for check in checks:
            executable = check.status.executable
            table.add_row(
                check.status.label,
                str(executable) if executable is not None else "not found",
                check.status.source or "",
            )
        return table

    def _advise(self, checks: Sequence[ToolCheck]) -> None:
        for check in checks:
            self._advise_one(check)

    def _advise_one(self, check: ToolCheck) -> None:
        state = check.state
        label = check.status.label

        if state is ToolState.MISSING:
            self._console.print(
                f"[muted]{label} installs itself on the next recording run[/muted]"
            )
        elif state is ToolState.DAMAGED:
            self._console.print(
                f"[danger]{label} is missing {check.status.missing_names}[/danger]"
            )
            self._console.print(f"[muted]{self._how_to_replace(check)}[/muted]")
        elif state is ToolState.OUTDATED:
            self._console.print(
                f"[warning]{label} {check.latest.shown} is out, "
                f"you are on {check.status.shown_version}[/warning]"
            )
            self._console.print(f"[muted]{self._how_to_replace(check)}[/muted]")
        elif state is ToolState.UNKNOWN and check.latest.error:
            self._console.print(f"[muted]{label}: {check.latest.error}[/muted]")

    @staticmethod
    def _how_to_replace(check: ToolCheck) -> str:
        if check.status.is_managed:
            return (
                f"delete {check.status.managed_root} and record once, "
                f"the new one downloads itself"
            )
        return (
            f"this one is not managed here, it came from {check.status.source}, "
            f"so replace it where you got it"
        )

    @staticmethod
    def _table(title: str) -> Table:
        return Table(
            title=f"[accent]{title}[/accent]",
            title_justify="left",
            header_style="accent",
            box=None,
            padding=(0, 2, 0, 0),
        )
