from __future__ import annotations

from rich.console import Console

from ..library import IndexingReport
from ..presentation.steps import DONE_MARK, Duration
from .catalogue import DemoCatalogue

NO_BUDGET = 0.0


class NewDemoReader:
    def __init__(self, console: Console, catalogue: DemoCatalogue) -> None:
        self._console = console
        self._catalogue = catalogue

    def read(self, budget_seconds: float | None = None) -> IndexingReport:
        waiting = self._catalogue.waiting()
        if not waiting:
            return IndexingReport()

        self._console.print(
            f"[muted]Reading {waiting} new demo(s) for the map and the nicknames[/muted]"
        )
        report = self._catalogue.catch_up(budget_seconds)
        self._announce(report)
        return report

    def _announce(self, report: IndexingReport) -> None:
        if not report.did_work:
            return

        body = f"{report.read} demo(s) read, {report.players} nickname(s)"
        if report.ran_out_of_time:
            body += f", {report.left} left for the next start"
        self._console.print(
            f"[success]{DONE_MARK}[/success] {body}  "
            f"[muted]{Duration.render(report.seconds)}[/muted]"
        )
