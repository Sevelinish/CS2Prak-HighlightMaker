from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path

from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from ..infrastructure.errors import DownloadError

CHUNK_SIZE = 1 << 16
USER_AGENT = "HighlighterCS2"


class FileDownloader:
    def __init__(self, console: Console, timeout_seconds: int) -> None:
        self._console = console
        self._timeout_seconds = timeout_seconds

    def download(self, url: str, destination: Path, label: str) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                total = self._content_length(response.headers.get("Content-Length"))
                self._stream(response, destination, label, total)
        except urllib.error.URLError as error:
            destination.unlink(missing_ok=True)
            raise DownloadError(f"Could not download {label} from {url}: {error}") from error

        if not destination.is_file() or destination.stat().st_size == 0:
            raise DownloadError(f"Downloaded {label} archive is empty")
        return destination

    def _stream(self, response, destination: Path, label: str, total: int | None) -> None:
        with self._build_progress() as progress:
            task = progress.add_task(label, total=total)
            with destination.open("wb") as target:
                while True:
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    target.write(chunk)
                    progress.update(task, advance=len(chunk))

    def _build_progress(self) -> Progress:
        return Progress(
            TextColumn("[brand]{task.description}[/brand]"),
            BarColumn(bar_width=32),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=self._console,
            transient=True,
        )

    @staticmethod
    def _content_length(raw: str | None) -> int | None:
        try:
            return int(raw) if raw else None
        except ValueError:
            return None
