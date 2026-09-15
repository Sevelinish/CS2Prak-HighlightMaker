from __future__ import annotations

from pathlib import Path

from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..media.assembler import AssembledClip
from ..media.reel import Reel
from ..plan.models import RecordingPlan
from ..recording.warm_session import WarmSession
from .steps import Duration

BYTES_PER_MEGABYTE = 1024 * 1024
SECONDS_PER_MINUTE = 60


class RunSummary:
    def __init__(self, console: Console) -> None:
        self._console = console

    def render(
        self,
        assembled: list[AssembledClip],
        plan: RecordingPlan,
        reel: Reel | None = None,
        warm_session: WarmSession | None = None,
    ) -> None:
        self._console.print()
        if not assembled:
            self._render_nothing()
            return

        self._console.print(self._table(assembled))
        if reel is not None:
            self._render_reel(reel)
        self._render_destination(assembled, plan)
        self._render_warm_session(warm_session)

    def _table(self, assembled: list[AssembledClip]) -> Table:
        table = Table(
            box=ROUNDED,
            border_style="muted",
            header_style="accent",
            title="[brand]Clips written[/brand]",
            title_justify="left",
        )
        table.add_column("#", justify="right", width=3)
        table.add_column("File", overflow="fold")
        table.add_column("Length", justify="right", width=8)
        table.add_column("Size", justify="right", width=9)
        table.add_column("Audio", justify="center", width=5)

        for index, clip in enumerate(assembled, start=1):
            table.add_row(
                str(index),
                clip.output.name,
                Duration.render(clip.clip.duration_seconds),
                self._size(clip.output),
                "[success]yes[/success]" if clip.has_audio else "[muted]no[/muted]",
            )
        return table

    def _render_reel(self, reel: Reel) -> None:
        self._console.print(
            f"[success]Joined into[/success] {reel.output.name} "
            f"[muted]{reel.clip_count} clips, {Duration.render(reel.duration_seconds)}, "
            f"{self._size(reel.output)}[/muted]"
        )

    def _render_destination(
        self, assembled: list[AssembledClip], plan: RecordingPlan
    ) -> None:
        folder = plan.output_directory / plan.demo_name
        self._console.print(
            f"[success]{len(assembled)}/{plan.clip_count} clips[/success] "
            f"[muted]saved to[/muted] {folder}"
        )

    def _render_warm_session(self, warm_session: WarmSession | None) -> None:
        if warm_session is None:
            return
        minutes = int(warm_session.seconds_left // SECONDS_PER_MINUTE)
        state = "waiting on the main menu" if warm_session.uses_netcon else "still on the demo"
        self._console.print()
        self._console.print(
            Panel(
                f"[accent]Counter-Strike 2 is still running[/accent] "
                f"[muted]pid {warm_session.pid}, {state}[/muted]\n"
                f"[muted]-exit0 again within {minutes} min skips the startup[/muted]",
                box=ROUNDED,
                border_style="muted",
                padding=(0, 2),
                expand=False,
            )
        )

    def _render_nothing(self) -> None:
        self._console.print(
            Panel(
                "[danger]No clips were produced[/danger]\n"
                "[muted]logs/highlighter.log has the details of what the game did[/muted]",
                box=ROUNDED,
                border_style="danger",
                padding=(0, 2),
                expand=False,
            )
        )

    @staticmethod
    def _size(path: Path) -> str:
        try:
            return f"{path.stat().st_size / BYTES_PER_MEGABYTE:.1f} MB"
        except OSError:
            return "?"
