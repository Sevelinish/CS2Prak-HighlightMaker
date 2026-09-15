from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from .geometry import EPSILON, CameraPlacement, Vector3
from .grenade import Grenade

FLIGHT_MODE = "flight"
THROWER_MODE = "thrower"
CAMERA_MODES = (FLIGHT_MODE, THROWER_MODE)
FLIGHT_REASON = "on the line the grenade flew in on"
THROWER_REASON = "on the line back to the thrower"
GROUP_MODE = "group"
GROUP_REASON = "pulled back to hold all {count} landings in frame"
MAXIMUM_ELEVATION_DEGREES = 55.0
MAXIMUM_GROUP_SPREAD = 600.0


@dataclass(frozen=True, slots=True)
class LandingShot:
    placement: CameraPlacement
    mode: str
    reason: str

    @property
    def follows_the_flight(self) -> bool:
        return self.mode == FLIGHT_MODE


class LandingCameraDirector:
    def __init__(
        self,
        distance: float,
        height: float,
        minimum_approach: float = 0.0,
        mode: str = FLIGHT_MODE,
        maximum_elevation: float = MAXIMUM_ELEVATION_DEGREES,
        maximum_spread: float = MAXIMUM_GROUP_SPREAD,
    ) -> None:
        self._distance = distance
        self._height = height
        self._minimum_approach = minimum_approach
        self._mode = mode if mode in CAMERA_MODES else FLIGHT_MODE
        self._maximum_elevation = maximum_elevation
        self._maximum_spread = maximum_spread

    @property
    def mode(self) -> str:
        return self._mode

    def direct(self, grenade: Grenade) -> LandingShot:
        if self._mode == FLIGHT_MODE:
            shot = self._from_flight(grenade)
            if shot is not None:
                return shot
        return self._from_thrower(grenade)

    def direct_group(self, grenades: Sequence[Grenade]) -> LandingShot:
        if len(grenades) == 1:
            return self.direct(grenades[0])

        centre = self._centre(grenades)
        spread = max(centre.distance_to(item.landing) for item in grenades)
        direction = self._group_direction(grenades)
        if direction is None or spread > self._maximum_spread:
            return self.direct(grenades[0])

        position = centre + direction.scaled(self._distance + spread)
        return LandingShot(
            placement=CameraPlacement(
                position=position, angles=position.angles_towards(centre)
            ),
            mode=GROUP_MODE,
            reason=GROUP_REASON.format(count=len(grenades)),
        )

    def _group_direction(self, grenades: Sequence[Grenade]) -> Vector3 | None:
        total = Vector3(0.0, 0.0, 0.0)
        found = 0
        for grenade in grenades:
            approach = grenade.flight.approach(self._distance)
            if approach is None or approach.distance < self._minimum_approach:
                continue
            total = total + approach.direction
            found += 1

        if found and total.length > EPSILON:
            return self._levelled(total.normalized())
        return self._levelled(self._thrower_direction(grenades))

    @staticmethod
    def _thrower_direction(grenades: Sequence[Grenade]) -> Vector3:
        centre = LandingCameraDirector._centre(grenades)
        return (grenades[0].thrower_position - centre).normalized()

    @staticmethod
    def _centre(grenades: Sequence[Grenade]) -> Vector3:
        total = Vector3(0.0, 0.0, 0.0)
        for grenade in grenades:
            total = total + grenade.landing
        return total.scaled(1.0 / len(grenades))

    def _from_flight(self, grenade: Grenade) -> LandingShot | None:
        approach = grenade.flight.approach(self._distance)
        if approach is None or approach.distance < self._minimum_approach:
            return None

        direction = self._levelled(approach.direction)
        if direction is None:
            return None

        position = grenade.landing + direction.scaled(self._distance)
        return LandingShot(
            placement=CameraPlacement(
                position=position, angles=position.angles_towards(grenade.landing)
            ),
            mode=FLIGHT_MODE,
            reason=FLIGHT_REASON,
        )

    def _from_thrower(self, grenade: Grenade) -> LandingShot:
        return LandingShot(
            placement=CameraPlacement.looking_at(
                target=grenade.landing,
                from_side=grenade.thrower_position,
                distance=self._distance,
                height=self._height,
            ),
            mode=THROWER_MODE,
            reason=THROWER_REASON,
        )

    def _levelled(self, direction: Vector3) -> Vector3 | None:
        horizontal = math.hypot(direction.x, direction.y)
        if horizontal < EPSILON:
            return None

        elevation = math.degrees(math.atan2(direction.z, horizontal))
        if elevation <= self._maximum_elevation:
            return direction

        wanted = math.radians(self._maximum_elevation)
        scale = math.cos(wanted) / horizontal
        return Vector3(direction.x * scale, direction.y * scale, math.sin(wanted))
