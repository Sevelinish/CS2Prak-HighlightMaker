from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..config.schema import ApplicationConfig
from ..infrastructure.errors import HighlighterError
from ..infrastructure.logging import get_logger
from ..infrastructure.paths import ApplicationPaths
from ..version import Version, __version__
from .checker import UpdateCheck, UpdateChecker
from .installer import UpdateInstaller
from .payload import UpdateError
from .swap import MARKER_NAME

UPDATE_DIRECTORY = "update"
NOTES_LINE_LIMIT = 6
BYTES_PER_MEGABYTE = 1024 * 1024


class UpdateService:
    def __init__(
        self, console: Console, paths: ApplicationPaths, config: ApplicationConfig
    ) -> None:
        self._console = console
        self._paths = paths
        self._config = config
        self._logger = get_logger("update")

    @property
    def marker_file(self) -> Path:
        work = self._paths.resolve(self._config.paths.work_directory)
        return work / UPDATE_DIRECTORY / MARKER_NAME

    def announce_installed(self) -> str:
        marker = self.marker_file
        if not marker.is_file():
            return ""
        try:
            installed = marker.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
        marker.unlink(missing_ok=True)
        if not installed:
            return ""
        self._console.print(
            f"[success]Updated to {installed}[/success] "
            f"[muted]your clips, demos and config.json were kept[/muted]"
        )
        return installed

    def check(self) -> UpdateCheck:
        return UpdateChecker(self._config.update, Version.current()).check()

    def run(self) -> bool:
        self._console.print(
            Panel(
                f"[brand]Checking for a newer HighlighterCS2[/brand]\n"
                f"[muted]you are on {__version__}[/muted]",
                border_style="muted",
                expand=False,
            )
        )
        try:
            check = self.check()
        except HighlighterError as error:
            self._console.print(f"[danger]Could not reach the release page[/danger]\n{error}")
            return False

        if check.is_unknown:
            self._console.print(
                "[warning]The latest release has no readable version tag[/warning]"
            )
            return False

        if not check.available:
            self._console.print(
                f"[success]You are up to date[/success] [muted]{check.current} is the latest[/muted]"
            )
            return True

        self._present(check)
        return self._install(check)

    def _present(self, check: UpdateCheck) -> None:
        release = check.release
        table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
        table.add_column(style="muted", justify="right")
        table.add_column()
        table.add_row("Installed", str(check.current))
        table.add_row("Available", f"[success]{check.latest}[/success]")
        if release is not None:
            table.add_row("Release", release.name or release.tag)
            table.add_row("File", release.asset_name)
            if release.size_bytes:
                table.add_row("Size", f"{release.size_bytes / BYTES_PER_MEGABYTE:.1f} MB")
            if release.published_at:
                table.add_row("Published", release.published_at.replace("T", " ").rstrip("Z"))

        self._console.print()
        self._console.print(table)
        self._print_notes(check)

    def _print_notes(self, check: UpdateCheck) -> None:
        release = check.release
        if release is None or not release.notes.strip():
            return

        lines = [line for line in release.notes.splitlines() if line.strip()]
        self._console.print()
        self._console.print("[accent]What is new[/accent]")
        for line in lines[:NOTES_LINE_LIMIT]:
            self._console.print(f"  [muted]{line.strip()}[/muted]")
        if len(lines) > NOTES_LINE_LIMIT:
            self._console.print(f"  [muted]... {len(lines) - NOTES_LINE_LIMIT} more line(s)[/muted]")

    def _install(self, check: UpdateCheck) -> bool:
        release = check.release
        if release is None:
            return False

        self._console.print()
        try:
            outcome = UpdateInstaller(self._console, self._paths, self._config).install(release)
        except UpdateError as error:
            self._console.print(f"[danger]{error}[/danger]")
            return False
        except HighlighterError as error:
            self._console.print(f"[danger]The update could not be downloaded[/danger]\n{error}")
            return False

        self._console.print(
            Panel(
                f"[success]Version {outcome.version} is ready to be installed[/success]\n"
                f"[muted]The program closes now and the files are swapped in a few seconds.\n"
                f"Your clips, demos, tools and config.json are left untouched.\n"
                f"Log: {outcome.log}[/muted]",
                border_style="success",
                expand=False,
            )
        )
        if not outcome.relaunch:
            self._console.print("[muted]Start HighlighterCS2 again once it is done.[/muted]")
        return True
