from __future__ import annotations

from pathlib import Path

from ..domain.match import Match
from ..infrastructure.logging import get_logger
from ..plan.models import ClipSegment, ClipSpec
from .audience import AudiencePicker, VoiceAudience
from .cues import VoiceTrackBuilder
from .mixer import VoiceMixer
from .packets import VoiceReader
from .utterance import DEFAULT_GAP_SECONDS, UtteranceGrouper

VOICE_FOLDER = "voice"


class VoiceOverlay:
    def __init__(
        self,
        match: Match,
        audience: VoiceAudience,
        work_directory: Path,
        mixer: VoiceMixer,
        gap_seconds: float = DEFAULT_GAP_SECONDS,
        reader: VoiceReader | None = None,
    ) -> None:
        self._match = match
        self._audience = audience
        self._directory = work_directory / VOICE_FOLDER / match.demo_name
        self._mixer = mixer
        self._gap_seconds = gap_seconds
        self._reader = reader or VoiceReader()
        self._picker = AudiencePicker(match)
        self._builder: VoiceTrackBuilder | None = None
        self._speakers = 0
        self._logger = get_logger("voice")

    @property
    def is_enabled(self) -> bool:
        return self._audience.is_on

    @property
    def speaker_count(self) -> int:
        return self._speakers

    def prepare(self) -> int:
        if self._builder is not None or not self.is_enabled:
            return self._speakers

        packets = self._reader.read(self._match.demo_path)
        utterances = UtteranceGrouper(self._match.tick_rate, self._gap_seconds).group(packets)
        self._speakers = len({item.steam_id64 for item in utterances})
        self._builder = VoiceTrackBuilder(
            tick_rate=self._match.tick_rate,
            utterances=utterances,
            directory=self._directory,
        )
        self._logger.info(
            "Voice from %s: %d utterance(s) by %d player(s)",
            self._match.demo_name,
            len(utterances),
            self._speakers,
        )
        return self._speakers

    def apply(self, clip: ClipSpec, segment: ClipSegment, audio: Path) -> Path:
        if not self.is_enabled:
            return audio

        self.prepare()
        builder = self._builder
        if builder is None:
            return audio

        track = builder.build(
            segment.start_tick, segment.end_tick, self._listeners(clip, segment)
        )
        if track.is_empty:
            return audio
        return self._mixer.mix(audio, track, VoiceMixer.destination_for(audio))

    def _listeners(self, clip: ClipSpec, segment: ClipSegment) -> frozenset[int]:
        player = segment.player or clip.player
        steam_id = player.steam_id64 if player is not None else 0
        return self._picker.listeners(self._audience, steam_id, clip.round_number)
