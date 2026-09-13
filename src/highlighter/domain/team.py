from __future__ import annotations

from enum import Enum


class TeamSide(Enum):
    TERRORIST = 2
    COUNTER_TERRORIST = 3

    @classmethod
    def from_team_number(cls, value: int | float | None) -> "TeamSide | None":
        try:
            return cls(int(value))
        except (TypeError, ValueError):
            return None

    @classmethod
    def from_label(cls, value: str | None) -> "TeamSide | None":
        if not isinstance(value, str):
            return None
        normalized = value.strip().upper()
        if normalized in {"T", "TERRORIST", "TERRORISTS", "2"}:
            return cls.TERRORIST
        if normalized in {"CT", "COUNTER-TERRORIST", "COUNTERTERRORIST", "3"}:
            return cls.COUNTER_TERRORIST
        return None

    @property
    def label(self) -> str:
        return "T" if self is TeamSide.TERRORIST else "CT"

    @property
    def opponent(self) -> "TeamSide":
        if self is TeamSide.TERRORIST:
            return TeamSide.COUNTER_TERRORIST
        return TeamSide.TERRORIST
