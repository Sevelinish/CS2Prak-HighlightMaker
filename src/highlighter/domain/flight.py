from __future__ import annotations

from dataclasses import dataclass

from .geometry import Vector3

RESTING_TOLERANCE = 1.0
STRAIGHTNESS_TOLERANCE = 1.8
STRAIGHTNESS_FLOOR = 60.0
MINIMUM_SEGMENT_LENGTH = 1.0
MAXIMUM_SAMPLES = 1024


@dataclass(frozen=True, slots=True)
class FlightPoint:
    tick: int
    position: Vector3


@dataclass(frozen=True, slots=True)
class Approach:
    point: Vector3
    distance: float
    direction: Vector3


@dataclass(frozen=True, slots=True)
class GrenadeFlight:
    points: tuple[FlightPoint, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.points

    @classmethod
    def of(cls, points: list[FlightPoint]) -> "GrenadeFlight":
        return cls(points=tuple(points[-MAXIMUM_SAMPLES:]))

    def moving(self) -> tuple[FlightPoint, ...]:
        if not self.points:
            return ()

        last = len(self.points) - 1
        while last > 0:
            previous = self.points[last - 1].position
            if previous.distance_to(self.points[last].position) > RESTING_TOLERANCE:
                break
            last -= 1
        return self.points[: last + 1]

    def approach(self, limit: float) -> Approach | None:
        moving = self.moving()
        if len(moving) < 2:
            return None

        landing = moving[-1].position
        travelled = 0.0
        found: Approach | None = None

        for index in range(len(moving) - 2, -1, -1):
            position = moving[index].position
            travelled += position.distance_to(moving[index + 1].position)
            straight = position.distance_to(landing)
            if straight < MINIMUM_SEGMENT_LENGTH:
                continue
            if straight >= STRAIGHTNESS_FLOOR and travelled > straight * STRAIGHTNESS_TOLERANCE:
                break
            found = Approach(
                point=position,
                distance=straight,
                direction=(position - landing).normalized(),
            )
            if straight >= limit:
                break
        return found
