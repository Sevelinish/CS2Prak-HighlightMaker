from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..infrastructure.logging import get_logger
from .assembler import AssembledClip
from .concat import ConcatMuxer
from .output_library import OutputLibrary


@dataclass(frozen=True, slots=True)
class Reel:
    output: Path
    clip_count: int
    duration_seconds: float


class ReelBuilder:
    def __init__(self, ffmpeg_executable: Path, library: OutputLibrary) -> None:
        self._muxer = ConcatMuxer(ffmpeg_executable)
        self._library = library
        self._logger = get_logger("media.reel")

    def build(self, clips: list[AssembledClip]) -> Reel | None:
        if not clips:
            return None

        destination = self._library.reel_destination()
        parts = [clip.output for clip in clips]

        if len(parts) == 1:
            destination.parent.mkdir(parents=True, exist_ok=True)
            parts[0].replace(destination)
        else:
            self._muxer.join(parts, destination)

        duration = sum(clip.clip.duration_seconds for clip in clips)
        self._logger.info(
            "Joined %d clip(s) into %s", len(clips), destination.name
        )
        return Reel(output=destination, clip_count=len(clips), duration_seconds=duration)
