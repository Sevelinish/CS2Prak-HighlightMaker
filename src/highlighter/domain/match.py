from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .player import Player
from .round import Round


@dataclass(slots=True)
class Match:
    demo_path: Path
    map_name: str
    tick_rate: int
    server_name: str = ""
    players: dict[int, Player] = field(default_factory=dict)
    rounds: list[Round] = field(default_factory=list)

    @property
    def demo_name(self) -> str:
        return self.demo_path.stem

    @property
    def round_count(self) -> int:
        return len(self.rounds)

    def ticks_to_seconds(self, ticks: int) -> float:
        return ticks / self.tick_rate if self.tick_rate else 0.0

    def seconds_to_ticks(self, seconds: float) -> int:
        return int(round(seconds * self.tick_rate))
