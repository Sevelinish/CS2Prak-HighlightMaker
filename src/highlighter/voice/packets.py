from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..infrastructure.logging import get_logger

FRAME_SECONDS = 0.01
FRAME_SAMPLES = 480
SAMPLE_RATE = 48000
TICK_KEY = "tick"
STEAM_KEY = "steamid"
PAYLOAD_KEY = "bytes"


@dataclass(frozen=True, slots=True)
class VoicePacket:
    tick: int
    steam_id64: int
    payload: bytes

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "VoicePacket | None":
        payload = source.get(PAYLOAD_KEY)
        if not isinstance(payload, (bytes, bytearray)) or not payload:
            return None
        try:
            return cls(
                tick=int(source[TICK_KEY]),
                steam_id64=int(source[STEAM_KEY]),
                payload=bytes(payload),
            )
        except (KeyError, TypeError, ValueError):
            return None


class VoiceReader:
    def __init__(self) -> None:
        self._logger = get_logger("voice")

    def read(self, demo_path: Path) -> tuple[VoicePacket, ...]:
        rows = self._rows(demo_path)
        if not rows:
            return ()

        collected = [VoicePacket.from_mapping(row) for row in rows if isinstance(row, Mapping)]
        packets = tuple(packet for packet in collected if packet is not None)
        self._logger.debug(
            "%s holds %d voice packet(s) from %d player(s)",
            demo_path.name,
            len(packets),
            len({packet.steam_id64 for packet in packets}),
        )
        return packets

    def _rows(self, demo_path: Path) -> Sequence[Any]:
        try:
            from demoparser2 import DemoParser

            rows = DemoParser(str(demo_path)).parse_voice()
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as error:
            self._logger.warning("No voice could be read from %s: %s", demo_path.name, error)
            return ()

        if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
            return rows
        self._logger.debug("parse_voice returned %s, which is not a list", type(rows))
        return ()
