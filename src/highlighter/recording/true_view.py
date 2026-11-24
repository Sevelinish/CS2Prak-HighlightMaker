from __future__ import annotations

from ..config.schema import RecordingConfig
from ..voice.audience import VoiceAudience

POV_CAPTURE_MODE = "pov"
FIRST_PERSON_MODE = "first_person"


class TrueViewProfile:
    @staticmethod
    def apply(recording: RecordingConfig) -> None:
        if not recording.true_view:
            return

        recording.capture_mode = POV_CAPTURE_MODE
        recording.spectator_mode = FIRST_PERSON_MODE
        if not VoiceAudience.parse(recording.voice_chat).is_on:
            recording.voice_chat = VoiceAudience.TEAM.value

    @staticmethod
    def audience(recording: RecordingConfig) -> VoiceAudience:
        return VoiceAudience.parse(recording.voice_chat)
