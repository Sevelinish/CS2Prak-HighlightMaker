from __future__ import annotations

from dataclasses import dataclass

from .player import Player
from .team import TeamSide
from .weapon import Weapon


@dataclass(frozen=True, slots=True)
class Kill:
    tick: int
    round_number: int
    attacker: Player
    victim: Player
    attacker_side: TeamSide | None
    victim_side: TeamSide | None
    weapon: Weapon
    headshot: bool
    wallbang: bool
    noscope: bool
    through_smoke: bool
    attacker_blind: bool
    attacker_airborne: bool
    distance: float
