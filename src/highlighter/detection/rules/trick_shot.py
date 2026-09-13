from __future__ import annotations

from typing import Callable, Iterable

from ...domain.highlight import Highlight, HighlightTag
from ...domain.kill import Kill
from ..context import RoundContext
from ..rule import HighlightRule

TRICK_PREDICATES: tuple[tuple[str, str, Callable[[Kill], bool]], ...] = (
    ("noscope", "noscope", lambda kill: kill.noscope and not kill.weapon.is_pistol),
    ("wallbang", "wallbang", lambda kill: kill.wallbang),
    ("through_smoke", "thru smoke", lambda kill: kill.through_smoke),
    ("blind_kill", "blind", lambda kill: kill.attacker_blind),
    ("airborne_kill", "in air", lambda kill: kill.attacker_airborne),
)


class TrickShotRule(HighlightRule):
    name = "trick_shot"

    def evaluate(self, context: RoundContext, candidate: Highlight) -> Iterable[HighlightTag]:
        tags: list[HighlightTag] = []
        for code, label, predicate in TRICK_PREDICATES:
            matches = sum(1 for kill in candidate.kills if predicate(kill))
            if not matches:
                continue
            display = label if matches == 1 else f"{label} x{matches}"
            tags.append(self._tag(code, display, multiplier=matches))
        return tags
