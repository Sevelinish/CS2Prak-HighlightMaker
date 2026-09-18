from __future__ import annotations

import subprocess
from pathlib import Path

from ..infrastructure.errors import EncodingError

FFMPEG_BASE_ARGUMENTS = ("-hide_banner", "-loglevel", "error", "-y")
LIST_SUFFIX = "_parts.txt"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class ConcatMuxer:
    def __init__(self, ffmpeg_executable: Path) -> None:
        self._ffmpeg_executable = ffmpeg_executable

    def join(self, parts: list[Path], target: Path) -> Path:
        if not parts:
            raise EncodingError(f"Nothing to join into {target.name}")
        if len(parts) == 1:
            return parts[0]

        listing = self._write_listing(parts, target)
        try:
            self.run(
                [
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(listing),
                    "-c",
                    "copy",
                    str(target),
                ],
                target.name,
            )
        finally:
            listing.unlink(missing_ok=True)
        return target

    def run(self, arguments: list[str], label: str) -> None:
        completed = subprocess.run(
            [str(self._ffmpeg_executable), *FFMPEG_BASE_ARGUMENTS, *arguments],
            capture_output=True,
            text=True,
            errors="replace",
            creationflags=NO_WINDOW,
        )
        if completed.returncode != 0:
            raise EncodingError(
                f"ffmpeg failed for {label}: {completed.stderr.strip()[:400]}"
            )

    @staticmethod
    def _write_listing(parts: list[Path], target: Path) -> Path:
        listing = target.with_name(f"{target.stem}{LIST_SUFFIX}")
        listing.parent.mkdir(parents=True, exist_ok=True)
        listing.write_text(
            "\n".join(f"file '{part.as_posix()}'" for part in parts) + "\n",
            encoding="utf-8",
        )
        return listing
