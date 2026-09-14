from __future__ import annotations

import math
from dataclasses import dataclass

EPSILON = 1e-6


@dataclass(frozen=True, slots=True)
class Vector3:
    x: float
    y: float
    z: float

    def __add__(self, other: "Vector3") -> "Vector3":
        return Vector3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vector3") -> "Vector3":
        return Vector3(self.x - other.x, self.y - other.y, self.z - other.z)

    def scaled(self, factor: float) -> "Vector3":
        return Vector3(self.x * factor, self.y * factor, self.z * factor)

    def raised(self, height: float) -> "Vector3":
        return Vector3(self.x, self.y, self.z + height)

    @property
    def length(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def normalized(self) -> "Vector3":
        length = self.length
        if length < EPSILON:
            return Vector3(1.0, 0.0, 0.0)
        return self.scaled(1.0 / length)

    def distance_to(self, other: "Vector3") -> float:
        return (self - other).length

    def angles_towards(self, target: "Vector3") -> "ViewAngles":
        delta = target - self
        horizontal = math.sqrt(delta.x * delta.x + delta.y * delta.y)
        yaw = math.degrees(math.atan2(delta.y, delta.x))
        pitch = -math.degrees(math.atan2(delta.z, horizontal or EPSILON))
        return ViewAngles(pitch=pitch, yaw=yaw)

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)

    def to_mapping(self) -> dict[str, float]:
        return {"x": round(self.x, 2), "y": round(self.y, 2), "z": round(self.z, 2)}


@dataclass(frozen=True, slots=True)
class ViewAngles:
    pitch: float
    yaw: float

    def to_mapping(self) -> dict[str, float]:
        return {"pitch": round(self.pitch, 2), "yaw": round(self.yaw, 2)}


@dataclass(frozen=True, slots=True)
class CameraPlacement:
    position: Vector3
    angles: ViewAngles

    @classmethod
    def looking_at(
        cls, target: Vector3, from_side: Vector3, distance: float, height: float
    ) -> "CameraPlacement":
        direction = (from_side - target).normalized()
        position = (target + direction.scaled(distance)).raised(height)
        return cls(position=position, angles=position.angles_towards(target))

    def to_mapping(self) -> dict[str, object]:
        return {"position": self.position.to_mapping(), "angles": self.angles.to_mapping()}
