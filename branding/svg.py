from __future__ import annotations

import re
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from pathlib import Path

COMMAND_PATTERN = re.compile(r"([A-Za-z])|(-?\d*\.?\d+(?:[eE][-+]?\d+)?)")
SUPPORTED_COMMANDS = "MmLlHhVvZz"
DEFAULT_COLOR = (0, 0, 0)
MINIMUM_CONTOUR_POINTS = 3


class UnsupportedPathError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Bounds:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @classmethod
    def around(cls, points) -> "Bounds":
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return cls(left=min(xs), top=min(ys), right=max(xs), bottom=max(ys))


@dataclass(frozen=True, slots=True)
class Shape:
    contours: tuple[tuple[tuple[float, float], ...], ...]
    color: tuple[int, int, int]

    @property
    def points(self) -> tuple[tuple[float, float], ...]:
        return tuple(point for contour in self.contours for point in contour)


@dataclass(frozen=True, slots=True)
class Drawing:
    shapes: tuple[Shape, ...]

    @property
    def bounds(self) -> Bounds:
        return Bounds.around([point for shape in self.shapes for point in shape.points])


class PathParser:
    def parse(self, definition: str) -> tuple[tuple[tuple[float, float], ...], ...]:
        contours: list[tuple[tuple[float, float], ...]] = []
        current: list[tuple[float, float]] = []
        command = ""
        numbers: list[float] = []
        cursor = (0.0, 0.0)
        start = (0.0, 0.0)

        for letter, number in COMMAND_PATTERN.findall(definition):
            if number:
                numbers.append(float(number))
                cursor, current = self._consume(command, numbers, cursor, current, start)
                if command in "Mm" and len(current) == 1:
                    start = cursor
                continue

            self._require_supported(letter)
            numbers = []
            if letter in "Zz":
                contours.append(tuple(current))
                current = []
                cursor = start
                command = ""
                continue

            if letter in "Mm" and current:
                contours.append(tuple(current))
                current = []
            command = letter

        if current:
            contours.append(tuple(current))
        return tuple(
            contour for contour in contours if len(contour) >= MINIMUM_CONTOUR_POINTS
        )

    def _consume(self, command, numbers, cursor, current, start):
        if command in "MmLl" and len(numbers) == 2:
            point = self._moved(command, cursor, numbers[0], numbers[1])
        elif command in "Hh" and len(numbers) == 1:
            point = self._moved(command, cursor, numbers[0], 0.0, vertical=False)
        elif command in "Vv" and len(numbers) == 1:
            point = self._moved(command, cursor, 0.0, numbers[0], horizontal=False)
        else:
            return cursor, current

        numbers.clear()
        return point, [*current, point]

    @staticmethod
    def _moved(
        command: str,
        cursor: tuple[float, float],
        x: float,
        y: float,
        horizontal: bool = True,
        vertical: bool = True,
    ) -> tuple[float, float]:
        relative = command.islower()
        moved_x = cursor[0] + x if relative else x
        moved_y = cursor[1] + y if relative else y
        return (
            moved_x if horizontal else cursor[0],
            moved_y if vertical else cursor[1],
        )

    @staticmethod
    def _require_supported(letter: str) -> None:
        if letter not in SUPPORTED_COMMANDS:
            raise UnsupportedPathError(
                f"The logo uses the path command '{letter}', "
                f"and only straight segments ({SUPPORTED_COMMANDS}) are understood"
            )


class SvgReader:
    def __init__(self, parser: PathParser | None = None) -> None:
        self._parser = parser or PathParser()

    def read(self, source: Path) -> Drawing:
        root = self._root(source)
        shapes = [
            Shape(contours=contours, color=self._color(element))
            for element, contours in self._paths(root)
            if contours
        ]
        if not shapes:
            raise UnsupportedPathError(f"{source} holds no filled paths")
        return Drawing(shapes=tuple(shapes))

    @staticmethod
    def _root(source: Path):
        try:
            return ElementTree.parse(source).getroot()
        except ElementTree.ParseError as error:
            raise UnsupportedPathError(f"{source} is not readable XML ({error})") from error

    def _paths(self, root):
        for element in root.iter():
            if self._local_name(element) != "path":
                continue
            definition = element.attrib.get("d", "")
            yield element, self._parser.parse(definition)

    @classmethod
    def _color(cls, element) -> tuple[int, int, int]:
        value = element.attrib.get("fill", "").strip()
        if not value.startswith("#"):
            return DEFAULT_COLOR
        return cls._from_hexadecimal(value[1:])

    @staticmethod
    def _from_hexadecimal(digits: str) -> tuple[int, int, int]:
        if len(digits) == 3:
            digits = "".join(digit * 2 for digit in digits)
        if len(digits) != 6:
            return DEFAULT_COLOR
        return (
            int(digits[0:2], 16),
            int(digits[2:4], 16),
            int(digits[4:6], 16),
        )

    @staticmethod
    def _local_name(element) -> str:
        return element.tag.rsplit("}", 1)[-1]
