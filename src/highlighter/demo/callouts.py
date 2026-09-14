from __future__ import annotations

import math

import pandas as pd
from demoparser2 import DemoParser

from ..domain.geometry import Vector3
from ..domain.grenade import UNKNOWN_PLACE
from ..infrastructure.logging import get_logger

PLACE_PROPERTY = "last_place_name"
POSITION_PROPERTIES = ["X", "Y", "Z"]
HEIGHT_WEIGHT = 2.0
MAXIMUM_MATCH_DISTANCE = 600.0


class CalloutAtlas:
    def __init__(self, samples: list[tuple[Vector3, str]]) -> None:
        self._samples = samples
        self._logger = get_logger("demo.callouts")

    @classmethod
    def build(cls, parser: DemoParser, ticks: list[int]) -> "CalloutAtlas":
        logger = get_logger("demo.callouts")
        if not ticks:
            return cls([])

        try:
            frame = parser.parse_ticks([*POSITION_PROPERTIES, PLACE_PROPERTY], ticks=ticks)
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as error:
            logger.warning("Callout lookup failed, places stay unknown: %s", error)
            return cls([])

        samples = cls._collect(frame)
        logger.debug(
            "Callout atlas: %d samples, %d places",
            len(samples),
            len({name for _, name in samples}),
        )
        return cls(samples)

    @staticmethod
    def _collect(frame: pd.DataFrame) -> list[tuple[Vector3, str]]:
        if frame is None or frame.empty or PLACE_PROPERTY not in frame.columns:
            return []

        samples: list[tuple[Vector3, str]] = []
        for record in frame.to_dict("records"):
            place = record.get(PLACE_PROPERTY)
            if not isinstance(place, str) or not place:
                continue
            try:
                point = Vector3(
                    float(record["X"]), float(record["Y"]), float(record["Z"])
                )
            except (KeyError, TypeError, ValueError):
                continue
            samples.append((point, place))
        return samples

    @property
    def places(self) -> set[str]:
        return {name for _, name in self._samples}

    def name_for(self, point: Vector3) -> str:
        best_name = UNKNOWN_PLACE
        best_distance = math.inf

        for sample, name in self._samples:
            distance = self._weighted_distance(point, sample)
            if distance < best_distance:
                best_distance, best_name = distance, name

        if best_distance > MAXIMUM_MATCH_DISTANCE:
            return UNKNOWN_PLACE
        return best_name

    @staticmethod
    def _weighted_distance(left: Vector3, right: Vector3) -> float:
        dx = left.x - right.x
        dy = left.y - right.y
        dz = (left.z - right.z) * HEIGHT_WEIGHT
        return math.sqrt(dx * dx + dy * dy + dz * dz)
