from __future__ import annotations

from ..config.schema import DetectionConfig
from .rule import HighlightRule
from .rules.clutch import ClutchRule
from .rules.multi_kill import MultiKillRule
from .rules.trick_shot import TrickShotRule
from .rules.weapon_feat import WeaponFeatRule

AVAILABLE_RULES: tuple[type[HighlightRule], ...] = (
    MultiKillRule,
    WeaponFeatRule,
    ClutchRule,
    TrickShotRule,
)


class RuleRegistry:
    def __init__(self, settings: DetectionConfig) -> None:
        self._settings = settings

    def build(self) -> list[HighlightRule]:
        enabled = set(self._settings.enabled_rules)
        return [
            rule_type(self._settings)
            for rule_type in AVAILABLE_RULES
            if rule_type.name in enabled
        ]
