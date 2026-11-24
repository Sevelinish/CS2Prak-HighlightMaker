from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ..infrastructure.logging import get_logger
from .ogg import OggOpusWriter
from .utterance import Utterance

OGG_SUFFIX = ".ogg"


@dataclass(frozen=True, slots=True)
class VoiceCue:
    source: Path
    offset_seconds: float = 0.0
    skip_seconds: float = 0.0
    speaker: int = 0

    @property
    def offset_milliseconds(self) -> int:
        return max(0, int(round(self.offset_seconds * 1000)))


@dataclass(frozen=True, slots=True)
class VoiceTrack:
    cues: tuple[VoiceCue, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.cues

    @property
    def speakers(self) -> frozenset[int]:
        return frozenset(cue.speaker for cue in self.cues)


class VoiceTrackBuilder:
    def __init__(
        self,
        tick_rate: int,
        utterances: Sequence[Utterance],
        directory: Path,
        writer: OggOpusWriter | None = None,
    ) -> None:
        self._tick_rate = max(1, tick_rate)
        self._utterances = tuple(utterances)
        self._directory = directory
        self._writer = writer or OggOpusWriter()
        self._written: dict[tuple[int, int], Path] = {}
        self._logger = get_logger("voice")

    def build(self, start_tick: int, end_tick: int, listeners: frozenset[int]) -> VoiceTrack:
        if not listeners or not self._utterances:
            return VoiceTrack()

        start = start_tick / self._tick_rate
        end = end_tick / self._tick_rate
        cues = [
            self._cue(utterance, start)
            for utterance in self._utterances
            if utterance.steam_id64 in listeners
            and utterance.overlaps(self._tick_rate, start, end)
        ]
        return VoiceTrack(cues=tuple(cue for cue in cues if cue is not None))

    def _cue(self, utterance: Utterance, start: float) -> VoiceCue | None:
        source = self._source_for(utterance)
        if source is None:
            return None

        relative = utterance.start_seconds(self._tick_rate) - start
        return VoiceCue(
            source=source,
            offset_seconds=max(0.0, relative),
            skip_seconds=max(0.0, -relative),
            speaker=utterance.steam_id64,
        )

    def _source_for(self, utterance: Utterance) -> Path | None:
        key = (utterance.steam_id64, utterance.start_tick)
        if key in self._written:
            return self._written[key]

        target = self._directory / f"{utterance.steam_id64}_{utterance.start_tick}{OGG_SUFFIX}"
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self._writer.render(utterance.payloads))
        except OSError as error:
            self._logger.debug("Could not write %s: %s", target.name, error)
            return None

        self._written[key] = target
        return target
