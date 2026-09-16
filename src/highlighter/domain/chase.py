from __future__ import annotations

from dataclasses import dataclass

from .flight import FlightPoint, GrenadeFlight, MINIMUM_SEGMENT_LENGTH
from .geometry import CameraPlacement, Vector3

MINIMUM_KEYFRAMES = 4
DEFAULT_FOV = 90.0


@dataclass(frozen=True, slots=True)
class PathKeyframe:
    seconds: float
    placement: CameraPlacement
    fov: float = DEFAULT_FOV

    def to_mapping(self) -> dict[str, float]:
        return {
            "seconds": round(self.seconds, 4),
            "x": round(self.placement.position.x, 2),
            "y": round(self.placement.position.y, 2),
            "z": round(self.placement.position.z, 2),
            "pitch": round(self.placement.angles.pitch, 2),
            "yaw": round(self.placement.angles.yaw, 2),
            "fov": round(self.fov, 2),
        }


@dataclass(frozen=True, slots=True)
class ChasePath:
    keyframes: tuple[PathKeyframe, ...] = ()
    start_tick: int = 0

    @property
    def is_usable(self) -> bool:
        return len(self.keyframes) >= MINIMUM_KEYFRAMES

    @property
    def seconds(self) -> float:
        if not self.keyframes:
            return 0.0
        return self.keyframes[-1].seconds - self.keyframes[0].seconds

    def to_mapping(self) -> list[dict[str, float]]:
        return [keyframe.to_mapping() for keyframe in self.keyframes]


class ChaseCameraDirector:
    def __init__(
        self,
        distance: float,
        height: float,
        stride: int,
        tick_rate: int,
        fov: float = DEFAULT_FOV,
    ) -> None:
        self._distance = distance
        self._height = height
        self._stride = max(1, stride)
        self._tick_rate = max(1, tick_rate)
        self._fov = fov

    def follow(self, flight: GrenadeFlight, hold_seconds: float = 0.0) -> ChasePath:
        moving = flight.moving()
        if len(moving) < 2:
            return ChasePath()

        first_tick = moving[0].tick
        keyframes = [
            self._keyframe(moving, index, first_tick)
            for index in self._sampled(len(moving))
        ]
        if len(keyframes) < MINIMUM_KEYFRAMES:
            return ChasePath()

        return ChasePath(
            keyframes=tuple(self._held(keyframes, hold_seconds)), start_tick=first_tick
        )

    def _sampled(self, count: int) -> list[int]:
        indexes = list(range(0, count, self._stride))
        if indexes[-1] != count - 1:
            indexes.append(count - 1)
        return indexes

    def _keyframe(
        self, moving: tuple[FlightPoint, ...], index: int, first_tick: int
    ) -> PathKeyframe:
        target = moving[index].position
        behind = self._behind(moving, index)
        position = behind.raised(self._height)
        return PathKeyframe(
            seconds=(moving[index].tick - first_tick) / self._tick_rate,
            placement=CameraPlacement(
                position=position, angles=position.angles_towards(target)
            ),
            fov=self._fov,
        )

    def _behind(self, moving: tuple[FlightPoint, ...], index: int) -> Vector3:
        target = moving[index].position
        travelled = 0.0

        for step in range(index, 0, -1):
            nearer = moving[step].position
            farther = moving[step - 1].position
            length = nearer.distance_to(farther)
            if length < MINIMUM_SEGMENT_LENGTH:
                continue
            if travelled + length >= self._distance:
                remaining = self._distance - travelled
                return nearer + (farther - nearer).scaled(remaining / length)
            travelled += length

        return self._extrapolated(moving, travelled)

    def _extrapolated(self, moving: tuple[FlightPoint, ...], travelled: float) -> Vector3:
        start = moving[0].position
        remaining = self._distance - travelled
        if remaining <= 0.0:
            return start

        forward = self._opening_direction(moving)
        if forward is None:
            return start
        return start - forward.scaled(remaining)

    @staticmethod
    def _opening_direction(moving: tuple[FlightPoint, ...]) -> Vector3 | None:
        start = moving[0].position
        for point in moving[1:]:
            step = point.position - start
            if step.length >= MINIMUM_SEGMENT_LENGTH:
                return step.normalized()
        return None

    @staticmethod
    def _held(keyframes: list[PathKeyframe], hold_seconds: float) -> list[PathKeyframe]:
        if hold_seconds <= 0.0:
            return keyframes
        last = keyframes[-1]
        return [
            *keyframes,
            PathKeyframe(
                seconds=last.seconds + hold_seconds,
                placement=last.placement,
                fov=last.fov,
            ),
        ]
