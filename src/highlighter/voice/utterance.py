from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from .packets import FRAME_SECONDS, VoicePacket

DEFAULT_GAP_SECONDS = 0.25


@dataclass(frozen=True, slots=True)
class Utterance:
    steam_id64: int
    start_tick: int
    payloads: tuple[bytes, ...] = ()

    @property
    def seconds(self) -> float:
        return len(self.payloads) * FRAME_SECONDS

    @property
    def is_empty(self) -> bool:
        return not self.payloads

    def end_seconds(self, tick_rate: int) -> float:
        return self.start_seconds(tick_rate) + self.seconds

    def start_seconds(self, tick_rate: int) -> float:
        return self.start_tick / tick_rate if tick_rate else 0.0

    def overlaps(self, tick_rate: int, start: float, end: float) -> bool:
        return self.start_seconds(tick_rate) < end and self.end_seconds(tick_rate) > start


class UtteranceGrouper:
    def __init__(self, tick_rate: int, gap_seconds: float = DEFAULT_GAP_SECONDS) -> None:
        self._gap_ticks = max(1, int(round(max(0.0, gap_seconds) * max(1, tick_rate))))

    def group(self, packets: Sequence[VoicePacket]) -> tuple[Utterance, ...]:
        collected: list[Utterance] = []
        for steam_id, owned in self._by_speaker(packets).items():
            collected.extend(self._runs(steam_id, owned))
        return tuple(sorted(collected, key=lambda item: (item.start_tick, item.steam_id64)))

    @staticmethod
    def _by_speaker(packets: Sequence[VoicePacket]) -> dict[int, list[VoicePacket]]:
        owned: dict[int, list[VoicePacket]] = {}
        for packet in packets:
            owned.setdefault(packet.steam_id64, []).append(packet)
        for series in owned.values():
            series.sort(key=lambda packet: packet.tick)
        return owned

    def _runs(self, steam_id: int, packets: Sequence[VoicePacket]) -> Iterable[Utterance]:
        payloads: list[bytes] = []
        start = packets[0].tick if packets else 0
        previous = start

        for packet in packets:
            if packet.tick - previous > self._gap_ticks and payloads:
                yield Utterance(steam_id, start, tuple(payloads))
                payloads = []
                start = packet.tick
            payloads.append(packet.payload)
            previous = packet.tick

        if payloads:
            yield Utterance(steam_id, start, tuple(payloads))
