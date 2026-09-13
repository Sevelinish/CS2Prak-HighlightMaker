from __future__ import annotations

from dataclasses import dataclass, field

from .kill import Kill
from .team import TeamSide


@dataclass(slots=True)
class Round:
    number: int
    freeze_end_tick: int
    end_tick: int
    winner: TeamSide | None
    end_reason: str | None
    roster: dict[int, TeamSide] = field(default_factory=dict)
    kills: list[Kill] = field(default_factory=list)

    def side_of(self, steam_id64: int) -> TeamSide | None:
        return self.roster.get(steam_id64)
