from __future__ import annotations

from enum import Enum

from ..domain.match import Match


class VoiceAudience(Enum):
    OFF = "off"
    TEAM = "team"
    EVERYONE = "everyone"

    @property
    def is_on(self) -> bool:
        return self is not VoiceAudience.OFF

    @classmethod
    def parse(cls, token: str | None) -> "VoiceAudience":
        normalized = (token or "").strip().lower()
        for audience in cls:
            if audience.value == normalized:
                return audience
        return cls.OFF

    @staticmethod
    def choices() -> tuple[str, ...]:
        return tuple(audience.value for audience in VoiceAudience)


class AudiencePicker:
    def __init__(self, match: Match) -> None:
        self._match = match
        self._rounds = {round_.number: round_ for round_ in match.rounds}

    def listeners(
        self, audience: VoiceAudience, point_of_view: int, round_number: int
    ) -> frozenset[int]:
        if not audience.is_on:
            return frozenset()
        if audience is VoiceAudience.EVERYONE:
            return frozenset(self._everyone())
        return frozenset(self._team_of(point_of_view, round_number))

    def _everyone(self) -> set[int]:
        return set(self._match.players)

    def _team_of(self, point_of_view: int, round_number: int) -> set[int]:
        roster = self._roster(round_number)
        side = roster.get(point_of_view)
        if side is None:
            return {point_of_view} if point_of_view else set()
        return {steam_id for steam_id, other in roster.items() if other is side}

    def _roster(self, round_number: int) -> dict:
        round_ = self._rounds.get(round_number)
        if round_ is not None and round_.roster:
            return dict(round_.roster)
        for candidate in self._match.rounds:
            if candidate.roster:
                return dict(candidate.roster)
        return {}
