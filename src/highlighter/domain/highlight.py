from __future__ import annotations

from dataclasses import dataclass, field

from .kill import Kill
from .player import Player
from .team import TeamSide


@dataclass(frozen=True, slots=True)
class HighlightTag:
    code: str
    label: str
    weight: float

    def __str__(self) -> str:
        return self.label


@dataclass(slots=True)
class Highlight:
    round_number: int
    player: Player
    side: TeamSide | None
    kills: tuple[Kill, ...]
    tags: tuple[HighlightTag, ...] = field(default_factory=tuple)

    @property
    def kill_count(self) -> int:
        return len(self.kills)

    @property
    def headshot_count(self) -> int:
        return sum(1 for kill in self.kills if kill.headshot)

    @property
    def first_tick(self) -> int:
        return min(kill.tick for kill in self.kills)

    @property
    def last_tick(self) -> int:
        return max(kill.tick for kill in self.kills)

    @property
    def score(self) -> float:
        return round(sum(tag.weight for tag in self.tags), 2)

    @property
    def tag_codes(self) -> tuple[str, ...]:
        return tuple(tag.code for tag in self.tags)

    @property
    def headline(self) -> str:
        return ", ".join(tag.label for tag in self.tags) or "kills"

    def with_tags(self, tags: tuple[HighlightTag, ...]) -> "Highlight":
        ordered = sorted(tags, key=lambda tag: tag.weight, reverse=True)
        return Highlight(
            round_number=self.round_number,
            player=self.player,
            side=self.side,
            kills=self.kills,
            tags=tuple(ordered),
        )
