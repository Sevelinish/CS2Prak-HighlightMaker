from __future__ import annotations

from pathlib import Path

from ..infrastructure.logging import get_logger
from ..media.concat import ConcatMuxer
from .cues import VoiceTrack

WAV_CODEC = "pcm_s16le"
MIXED_SUFFIX = "_voice.wav"
DEFAULT_VOLUME = 1.4


class VoiceMixer:
    def __init__(
        self,
        ffmpeg_executable: Path,
        volume: float = DEFAULT_VOLUME,
        muxer: ConcatMuxer | None = None,
    ) -> None:
        self._volume = max(0.0, volume)
        self._muxer = muxer or ConcatMuxer(ffmpeg_executable)
        self._logger = get_logger("voice")

    def mix(self, base: Path, track: VoiceTrack, destination: Path) -> Path:
        if track.is_empty or self._volume <= 0.0:
            return base

        arguments = ["-i", str(base)]
        for cue in track.cues:
            if cue.skip_seconds > 0.0:
                arguments.extend(["-ss", f"{cue.skip_seconds:.3f}"])
            arguments.extend(["-i", str(cue.source)])

        arguments.extend(
            [
                "-filter_complex",
                self._graph(track),
                "-map",
                "[mixed]",
                "-c:a",
                WAV_CODEC,
                str(destination),
            ]
        )
        self._muxer.run(arguments, destination.name)
        self._logger.debug(
            "Mixed %d voice cue(s) from %d speaker(s) into %s",
            len(track.cues),
            len(track.speakers),
            destination.name,
        )
        return destination

    def _graph(self, track: VoiceTrack) -> str:
        chains = []
        labels = []
        for index, cue in enumerate(track.cues, start=1):
            label = f"v{index}"
            chains.append(
                f"[{index}:a]adelay={cue.offset_milliseconds}:all=1,"
                f"volume={self._volume:g}[{label}]"
            )
            labels.append(f"[{label}]")

        inputs = len(track.cues) + 1
        chains.append(
            f"[0:a]{''.join(labels)}amix=inputs={inputs}:duration=first:normalize=0[mixed]"
        )
        return ";".join(chains)

    @staticmethod
    def destination_for(base: Path) -> Path:
        return base.with_name(f"{base.stem}{MIXED_SUFFIX}")
