from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .flight import GrenadeFlight
from .geometry import Vector3, ViewAngles
from .player import Player
from .team import TeamSide

UNKNOWN_PLACE = "unknown"


class GrenadeKind(Enum):
    SMOKE = "smoke"
    FLASH = "flash"
    HE = "he"
    MOLOTOV = "molotov"
    DECOY = "decoy"

    @property
    def detonate_event(self) -> str:
        return _DETONATE_EVENTS[self]

    @property
    def projectile_class(self) -> str:
        return _PROJECTILE_CLASSES[self]

    @property
    def label(self) -> str:
        return _LABELS[self]

    @classmethod
    def from_token(cls, token: str) -> "GrenadeKind | None":
        normalized = token.strip().lower()
        for kind in cls:
            if normalized == kind.value:
                return kind
        return _ALIASES.get(normalized)

    @classmethod
    def tokens(cls) -> tuple[str, ...]:
        return tuple(kind.value for kind in cls)


_DETONATE_EVENTS = {
    GrenadeKind.SMOKE: "smokegrenade_detonate",
    GrenadeKind.FLASH: "flashbang_detonate",
    GrenadeKind.HE: "hegrenade_detonate",
    GrenadeKind.MOLOTOV: "inferno_startburn",
    GrenadeKind.DECOY: "decoy_started",
}
_PROJECTILE_CLASSES = {
    GrenadeKind.SMOKE: "CSmokeGrenadeProjectile",
    GrenadeKind.FLASH: "CFlashbangProjectile",
    GrenadeKind.HE: "CHEGrenadeProjectile",
    GrenadeKind.MOLOTOV: "CMolotovProjectile",
    GrenadeKind.DECOY: "CDecoyProjectile",
}
_LABELS = {
    GrenadeKind.SMOKE: "smoke",
    GrenadeKind.FLASH: "flash",
    GrenadeKind.HE: "he",
    GrenadeKind.MOLOTOV: "molotov",
    GrenadeKind.DECOY: "decoy",
}
_ALIASES = {
    "smokes": GrenadeKind.SMOKE,
    "flashes": GrenadeKind.FLASH,
    "flashbang": GrenadeKind.FLASH,
    "grenade": GrenadeKind.HE,
    "frag": GrenadeKind.HE,
    "hegrenade": GrenadeKind.HE,
    "molly": GrenadeKind.MOLOTOV,
    "molotovs": GrenadeKind.MOLOTOV,
    "incendiary": GrenadeKind.MOLOTOV,
    "fire": GrenadeKind.MOLOTOV,
    "decoys": GrenadeKind.DECOY,
}


@dataclass(slots=True)
class Grenade:
    kind: GrenadeKind
    round_number: int
    thrower: Player
    side: TeamSide | None
    throw_tick: int
    detonate_tick: int
    thrower_position: Vector3
    thrower_angles: ViewAngles
    landing: Vector3
    landing_place: str = UNKNOWN_PLACE
    round_time_seconds: float = 0.0
    flight: GrenadeFlight = field(default_factory=GrenadeFlight)

    @property
    def flight_ticks(self) -> int:
        return max(0, self.detonate_tick - self.throw_tick)

    @property
    def setpos_command(self) -> str:
        return (
            f"setpos {self.thrower_position.x:.2f} "
            f"{self.thrower_position.y:.2f} {self.thrower_position.z:.2f}"
        )

    @property
    def setang_command(self) -> str:
        return f"setang {self.thrower_angles.pitch:.2f} {self.thrower_angles.yaw:.2f}"

    @property
    def round_clock(self) -> str:
        minutes, seconds = divmod(int(self.round_time_seconds), 60)
        return f"{minutes}:{seconds:02d}"
