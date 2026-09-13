from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config.schema import EncodingConfig
from ..infrastructure.logging import get_logger
from ..plan.models import ClipSegment, ClipSpec, RecordingPlan
from .concat import ConcatMuxer
from .encoders import EncoderProfile
from .output_library import OutputLibrary

VIDEO_SUFFIXES = (".mp4", ".mkv", ".mov", ".avi")
AUDIO_SUFFIXES = (".wav", ".flac")


@dataclass(frozen=True, slots=True)
class RecordedSegment:
    segment: ClipSegment
    video: Path
    audio: Path | None


@dataclass(frozen=True, slots=True)
class AssembledClip:
    clip: ClipSpec
    output: Path
    has_audio: bool
    segment_count: int


class ClipAssembler:
    def __init__(
        self,
        ffmpeg_executable: Path,
        encoding: EncodingConfig,
        encoder: EncoderProfile,
        take_directory: Path,
        library: OutputLibrary,
        video_filter: str = "",
    ) -> None:
        self._ffmpeg_executable = ffmpeg_executable
        self._encoding = encoding
        self._encoder = encoder
        self._take_directory = take_directory
        self._library = library
        self._video_filter = video_filter
        self._muxer = ConcatMuxer(ffmpeg_executable)
        self._logger = get_logger("media")

    def assemble(self, plan: RecordingPlan) -> list[AssembledClip]:
        self._library.prepare()
        assembled: list[AssembledClip] = []

        for clip in plan.clips:
            recorded = self._collect(clip)
            if not recorded:
                self._logger.warning("No recorded video found for clip %s", clip.name)
                continue

            destination = self._library.destination_for(clip.name)
            has_audio = self._render(clip, recorded, destination)
            assembled.append(
                AssembledClip(
                    clip=clip,
                    output=destination,
                    has_audio=has_audio,
                    segment_count=len(recorded),
                )
            )
            self._logger.info(
                "Rendered %s from %d segment(s)", destination.name, len(recorded)
            )

        return assembled

    def _collect(self, clip: ClipSpec) -> list[RecordedSegment]:
        recorded: list[RecordedSegment] = []
        for segment in clip.segments:
            root = self._take_directory / clip.name / segment.name
            video = self._largest_file(root, VIDEO_SUFFIXES)
            if video is None:
                self._logger.warning(
                    "Segment %s of clip %s produced no video", segment.name, clip.name
                )
                continue
            recorded.append(
                RecordedSegment(
                    segment=segment,
                    video=video,
                    audio=self._largest_file(root, AUDIO_SUFFIXES),
                )
            )
        return recorded

    def _render(
        self, clip: ClipSpec, recorded: list[RecordedSegment], destination: Path
    ) -> bool:
        if len(recorded) == 1:
            return self._mux(recorded[0], destination)

        joined_video = self._concatenate(clip, [item.video for item in recorded])
        joined_audio = self._concatenate_audio(clip, recorded)
        return self._mux(
            RecordedSegment(recorded[0].segment, joined_video, joined_audio), destination
        )

    def _concatenate(self, clip: ClipSpec, parts: list[Path]) -> Path:
        target = self._take_directory / clip.name / f"joined{parts[0].suffix}"
        self._muxer.join(parts, target)
        return target

    def _concatenate_audio(
        self, clip: ClipSpec, recorded: list[RecordedSegment]
    ) -> Path | None:
        tracks = [item.audio for item in recorded if item.audio is not None]
        if len(tracks) != len(recorded):
            return None
        target = self._take_directory / clip.name / f"joined{tracks[0].suffix}"
        self._muxer.join(tracks, target)
        return target

    def _mux(self, recorded: RecordedSegment, destination: Path) -> bool:
        arguments = ["-i", str(recorded.video)]
        if recorded.audio is not None:
            arguments.extend(["-i", str(recorded.audio)])

        arguments.extend(self._video_arguments())
        if recorded.audio is not None:
            arguments.extend(
                [
                    "-c:a",
                    self._encoding.audio_codec,
                    "-b:a",
                    self._encoding.audio_bitrate,
                    "-shortest",
                ]
            )
        arguments.extend(["-movflags", "+faststart", str(destination)])

        self._muxer.run(arguments, destination.name)
        return recorded.audio is not None

    def _video_arguments(self) -> list[str]:
        if not self._video_filter:
            return ["-c:v", "copy"]
        return ["-vf", self._video_filter, *self._encoder.output_arguments()]

    @staticmethod
    def _largest_file(root: Path, suffixes: tuple[str, ...]) -> Path | None:
        if not root.is_dir():
            return None
        candidates = [
            candidate
            for candidate in root.rglob("*")
            if candidate.is_file() and candidate.suffix.lower() in suffixes
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda candidate: candidate.stat().st_size)
