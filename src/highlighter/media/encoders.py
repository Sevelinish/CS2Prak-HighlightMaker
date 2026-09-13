from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..config.schema import EncodingConfig
from ..infrastructure.logging import get_logger

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PROBE_TIMEOUT_SECONDS = 30
SOFTWARE_CODEC = "libx264"


@dataclass(frozen=True, slots=True)
class EncoderProfile:
    codec: str
    arguments: tuple[str, ...]
    container: str
    is_hardware: bool

    def output_arguments(self) -> tuple[str, ...]:
        return self.arguments


def _libx264_arguments(settings: EncodingConfig) -> tuple[str, ...]:
    return (
        "-c:v",
        "libx264",
        "-preset",
        settings.preset,
        "-crf",
        str(settings.quality),
        "-pix_fmt",
        settings.pixel_format,
    )


def _nvenc_arguments(settings: EncodingConfig) -> tuple[str, ...]:
    return (
        "-c:v",
        "h264_nvenc",
        "-preset",
        "p4",
        "-tune",
        "hq",
        "-rc",
        "vbr",
        "-cq",
        str(settings.quality),
        "-b:v",
        "0",
        "-pix_fmt",
        settings.pixel_format,
    )


def _amf_arguments(settings: EncodingConfig) -> tuple[str, ...]:
    return (
        "-c:v",
        "h264_amf",
        "-quality",
        "balanced",
        "-rc",
        "cqp",
        "-qp_i",
        str(settings.quality),
        "-qp_p",
        str(settings.quality),
        "-pix_fmt",
        settings.pixel_format,
    )


def _qsv_arguments(settings: EncodingConfig) -> tuple[str, ...]:
    return (
        "-c:v",
        "h264_qsv",
        "-preset",
        "faster",
        "-global_quality",
        str(settings.quality),
        "-pix_fmt",
        "nv12",
    )


ARGUMENT_BUILDERS: dict[str, Callable[[EncodingConfig], tuple[str, ...]]] = {
    "libx264": _libx264_arguments,
    "h264_nvenc": _nvenc_arguments,
    "h264_amf": _amf_arguments,
    "h264_qsv": _qsv_arguments,
}
HARDWARE_CODECS = frozenset({"h264_nvenc", "h264_amf", "h264_qsv"})


class EncoderSelector:
    def __init__(self, ffmpeg_executable: Path, settings: EncodingConfig) -> None:
        self._ffmpeg_executable = ffmpeg_executable
        self._settings = settings
        self._logger = get_logger("media.encoder")

    def select(self) -> EncoderProfile:
        for codec in self._candidates():
            if codec not in ARGUMENT_BUILDERS:
                self._logger.debug("Skipping unknown codec %s", codec)
                continue
            if not self._can_encode(codec):
                continue
            return self._build(codec)

        self._logger.warning("No preferred encoder worked, falling back to %s", SOFTWARE_CODEC)
        return self._build(SOFTWARE_CODEC)

    def _candidates(self) -> list[str]:
        if self._settings.video_codec != "auto":
            return [self._settings.video_codec, SOFTWARE_CODEC]
        return [*self._settings.preferred_codecs, SOFTWARE_CODEC]

    def _build(self, codec: str) -> EncoderProfile:
        arguments = list(ARGUMENT_BUILDERS[codec](self._settings))
        arguments.extend(self._settings.extra_output_arguments)
        return EncoderProfile(
            codec=codec,
            arguments=tuple(arguments),
            container=self._settings.container,
            is_hardware=codec in HARDWARE_CODECS,
        )

    def _can_encode(self, codec: str) -> bool:
        arguments = [
            str(self._ffmpeg_executable),
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x240:r=30",
            "-frames:v",
            "1",
            *ARGUMENT_BUILDERS[codec](self._settings),
            "-f",
            "null",
            "-",
        ]

        try:
            completed = subprocess.run(
                arguments,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=PROBE_TIMEOUT_SECONDS,
                creationflags=NO_WINDOW,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False

        if completed.returncode == 0:
            self._logger.debug("Encoder %s is usable", codec)
            return True

        self._logger.debug(
            "Encoder %s unavailable: %s", codec, completed.stderr.strip().splitlines()[:1]
        )
        return False
