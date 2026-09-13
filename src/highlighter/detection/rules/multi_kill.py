from __future__ import annotations

from typing import Iterable

from ...domain.highlight import Highlight, HighlightTag
from ..context import RoundContext
from ..rule import HighlightRule

KILL_LABELS = {
    2: "2K",
    3: "3K",
    4: "4K",
    5: "ACE",
}


class MultiKillRule(HighlightRule):
    name = "multi_kill"

    def evaluate(self, context: RoundContext, candidate: Highlight) -> Iterable[HighlightTag]:
        kill_count = min(candidate.kill_count, 5)
        if kill_count < 2:
            return []

        tags = [self._tag(f"kills_{kill_count}", KILL_LABELS[kill_count])]

        if candidate.headshot_count == candidate.kill_count and candidate.kill_count >= 2:
            tags.append(self._tag("headshot_only", "all headshots"))

        if context.is_pistol_round:
            tags.append(self._tag("pistol_round", "pistol round"))

        return tags
