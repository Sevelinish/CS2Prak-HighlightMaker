from __future__ import annotations

from typing import Iterable

from ...domain.highlight import Highlight, HighlightTag
from ..context import RoundContext
from ..rule import HighlightRule

MAXIMUM_CLUTCH_OPPONENTS = 5


class ClutchRule(HighlightRule):
    name = "clutch"

    def evaluate(self, context: RoundContext, candidate: Highlight) -> Iterable[HighlightTag]:
        situation = context.clutch_of(candidate.player.steam_id64)
        if situation is None or not situation.won:
            return []

        opponents = min(situation.opponents, MAXIMUM_CLUTCH_OPPONENTS)
        return [self._tag(f"clutch_1v{opponents}", f"clutch 1v{opponents}")]
