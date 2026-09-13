from __future__ import annotations

from typing import Iterable

from ...domain.highlight import Highlight, HighlightTag
from ..context import RoundContext
from ..rule import HighlightRule

AWP_DOUBLE_THRESHOLD = 2
AWP_MULTI_THRESHOLD = 3
PISTOL_MULTI_THRESHOLD = 3


class WeaponFeatRule(HighlightRule):
    name = "weapon_feat"

    def evaluate(self, context: RoundContext, candidate: Highlight) -> Iterable[HighlightTag]:
        tags: list[HighlightTag] = []
        kills = candidate.kills

        awp_kills = [kill for kill in kills if kill.weapon.is_awp]
        if len(awp_kills) >= AWP_MULTI_THRESHOLD:
            tags.append(self._tag("awp_multi", f"AWP {len(awp_kills)}K"))
        elif len(awp_kills) >= AWP_DOUBLE_THRESHOLD:
            tags.append(self._tag("awp_double", f"AWP {len(awp_kills)}K"))

        sniper_noscopes = [kill for kill in kills if kill.weapon.is_sniper and kill.noscope]
        if len(sniper_noscopes) >= AWP_DOUBLE_THRESHOLD:
            tags.append(self._tag("sniper_noscope_multi", f"noscope {len(sniper_noscopes)}K"))

        knife_kills = [kill for kill in kills if kill.weapon.is_knife]
        if knife_kills:
            tags.append(self._tag("knife_kill", "knife", multiplier=len(knife_kills)))

        taser_kills = [kill for kill in kills if kill.weapon.is_taser]
        if taser_kills:
            tags.append(self._tag("zeus_kill", "zeus", multiplier=len(taser_kills)))

        deagle_headshots = [
            kill for kill in kills if kill.weapon.is_deagle and kill.headshot
        ]
        if deagle_headshots:
            tags.append(
                self._tag("deagle_headshot", f"deagle HS x{len(deagle_headshots)}")
                if len(deagle_headshots) > 1
                else self._tag("deagle_headshot", "deagle HS")
            )

        pistol_kills = [kill for kill in kills if kill.weapon.is_pistol]
        if len(pistol_kills) >= PISTOL_MULTI_THRESHOLD:
            tags.append(self._tag("pistol_multi", f"pistol {len(pistol_kills)}K"))

        grenade_kills = [kill for kill in kills if kill.weapon.is_grenade]
        if grenade_kills:
            tags.append(self._tag("grenade_kill", "nade", multiplier=len(grenade_kills)))

        return tags
