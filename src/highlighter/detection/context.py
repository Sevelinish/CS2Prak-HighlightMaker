from __future__ import annotations

from dataclasses import dataclass

from ..domain.round import Round
from ..domain.team import TeamSide

MINIMUM_CLUTCH_OPPONENTS = 2


@dataclass(frozen=True, slots=True)
class ClutchSituation:
    steam_id64: int
    opponents: int
    won: bool


class RoundContext:
    def __init__(self, round_: Round, is_pistol_round: bool) -> None:
        self._round = round_
        self._is_pistol_round = is_pistol_round
        self._clutches = self._detect_clutches()

    @property
    def round(self) -> Round:
        return self._round

    @property
    def is_pistol_round(self) -> bool:
        return self._is_pistol_round

    def clutch_of(self, steam_id64: int) -> ClutchSituation | None:
        return self._clutches.get(steam_id64)

    def _detect_clutches(self) -> dict[int, ClutchSituation]:
        if not self._round.roster:
            return {}

        alive: dict[TeamSide, set[int]] = {
            TeamSide.TERRORIST: set(),
            TeamSide.COUNTER_TERRORIST: set(),
        }
        for steam_id, side in self._round.roster.items():
            alive[side].add(steam_id)

        situations: dict[int, ClutchSituation] = {}
        for kill in self._round.kills:
            victim_side = self._round.side_of(kill.victim.steam_id64)
            if victim_side is None:
                continue
            alive[victim_side].discard(kill.victim.steam_id64)
            self._record_lone_survivors(alive, situations)

        return situations

    def _record_lone_survivors(
        self, alive: dict[TeamSide, set[int]], situations: dict[int, ClutchSituation]
    ) -> None:
        for side, survivors in alive.items():
            if len(survivors) != 1:
                continue
            opponents = len(alive[side.opponent])
            if opponents < MINIMUM_CLUTCH_OPPONENTS:
                continue
            steam_id = next(iter(survivors))
            existing = situations.get(steam_id)
            if existing is not None and existing.opponents >= opponents:
                continue
            situations[steam_id] = ClutchSituation(
                steam_id64=steam_id,
                opponents=opponents,
                won=self._round.winner is side,
            )
