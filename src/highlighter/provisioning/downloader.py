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

    def download(
        self, url: str, destination: Path, label: str, expected_bytes: int = 0
    ) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                announced = self._content_length(response.headers.get("Content-Length"))
                written = self._stream(response, destination, label, announced)
        except (urllib.error.URLError, OSError) as error:
            destination.unlink(missing_ok=True)
            raise DownloadError(f"Could not download {label} from {url}: {error}") from error

        self._verify(destination, label, written, announced, expected_bytes)
        return destination

    def _verify(
        self,
        destination: Path,
        label: str,
        written: int,
        announced: int | None,
        expected_bytes: int,
    ) -> None:
        if not destination.is_file() or written == 0:
            destination.unlink(missing_ok=True)
            raise DownloadError(f"Downloaded {label} archive is empty")

        wanted = announced or expected_bytes
        if wanted and written != wanted:
            destination.unlink(missing_ok=True)
            raise DownloadError(
                f"{label} arrived incomplete: got {written:,} of {wanted:,} bytes. "
                f"Check the connection and try again."
            )

    def _stream(self, response, destination: Path, label: str, total: int | None) -> int:
        written = 0
        with self._build_progress() as progress:
            task = progress.add_task(label, total=total)
            with destination.open("wb") as target:
                while True:
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    target.write(chunk)
                    written += len(chunk)
                    progress.update(task, advance=len(chunk))
        return written

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
