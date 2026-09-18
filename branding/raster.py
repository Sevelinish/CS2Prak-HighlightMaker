from __future__ import annotations

from dataclasses import dataclass

from .svg import Bounds, Drawing, Shape

CHANNELS = 4
OPAQUE = 255
DEFAULT_MARGIN = 0.04
DEFAULT_SAMPLES = 2


@dataclass(frozen=True, slots=True)
class Bitmap:
    width: int
    height: int
    pixels: bytes

    def pixel(self, x: int, y: int) -> tuple[int, int, int, int]:
        start = (y * self.width + x) * CHANNELS
        red, green, blue, alpha = self.pixels[start : start + CHANNELS]
        return red, green, blue, alpha

    def rows(self):
        stride = self.width * CHANNELS
        for index in range(self.height):
            yield self.pixels[index * stride : (index + 1) * stride]

    def resized(self, size: int) -> "Bitmap":
        if size == self.width and size == self.height:
            return self
        return _AreaResampler(self).to(size)


class Placement:
    def __init__(self, bounds: Bounds, size: int, margin: float = DEFAULT_MARGIN) -> None:
        usable = size * (1.0 - 2.0 * margin)
        self._scale = min(
            usable / bounds.width if bounds.width else usable,
            usable / bounds.height if bounds.height else usable,
        )
        self._offset_x = (size - bounds.width * self._scale) / 2.0 - bounds.left * self._scale
        self._offset_y = (size - bounds.height * self._scale) / 2.0 - bounds.top * self._scale

    def to_device(self, point: tuple[float, float]) -> tuple[float, float]:
        return (
            point[0] * self._scale + self._offset_x,
            point[1] * self._scale + self._offset_y,
        )


class Rasterizer:
    def __init__(self, samples: int = DEFAULT_SAMPLES, margin: float = DEFAULT_MARGIN) -> None:
        self._samples = max(1, samples)
        self._margin = margin

    def render(self, drawing: Drawing, size: int) -> Bitmap:
        placement = Placement(drawing.bounds, size, self._margin)
        canvas = _Canvas(size)
        for shape in drawing.shapes:
            canvas.paint(shape.color, self._coverage(shape, placement, size))
        return canvas.to_bitmap()

    def _coverage(self, shape: Shape, placement: Placement, size: int) -> list[float]:
        coverage = [0.0] * (size * size)
        edges = self._edges(shape, placement)
        if not edges:
            return coverage

        weight = 1.0 / self._samples
        for row in range(size * self._samples):
            height = (row + 0.5) / self._samples
            crossings = sorted(self._crossings(edges, height))
            line = (row // self._samples) * size
            for index in range(0, len(crossings) - 1, 2):
                self._fill(coverage, line, crossings[index], crossings[index + 1], size, weight)
        return [value if value < 1.0 else 1.0 for value in coverage]

    @staticmethod
    def _edges(shape: Shape, placement: Placement) -> list[tuple[float, float, float, float]]:
        edges: list[tuple[float, float, float, float]] = []
        for contour in shape.contours:
            points = [placement.to_device(point) for point in contour]
            for index, first in enumerate(points):
                second = points[(index + 1) % len(points)]
                if first[1] != second[1]:
                    edges.append((first[0], first[1], second[0], second[1]))
        return edges

    @staticmethod
    def _crossings(edges, height: float) -> list[float]:
        found: list[float] = []
        for x0, y0, x1, y1 in edges:
            if (y0 <= height < y1) or (y1 <= height < y0):
                found.append(x0 + (height - y0) * (x1 - x0) / (y1 - y0))
        return found

    @staticmethod
    def _fill(
        coverage: list[float], line: int, start: float, end: float, size: int, weight: float
    ) -> None:
        start = max(0.0, start)
        end = min(float(size), end)
        if end <= start:
            return

        first = int(start)
        last = min(size - 1, int(end) if end > int(end) else int(end) - 1)
        for column in range(first, last + 1):
            covered = min(end, column + 1.0) - max(start, float(column))
            if covered > 0.0:
                coverage[line + column] += covered * weight


class _Canvas:
    def __init__(self, size: int) -> None:
        self._size = size
        self._red = [0.0] * (size * size)
        self._green = [0.0] * (size * size)
        self._blue = [0.0] * (size * size)
        self._alpha = [0.0] * (size * size)

    def paint(self, color: tuple[int, int, int], coverage: list[float]) -> None:
        red, green, blue = color
        for index, alpha in enumerate(coverage):
            if alpha <= 0.0:
                continue
            remainder = 1.0 - alpha
            self._red[index] = red * alpha + self._red[index] * remainder
            self._green[index] = green * alpha + self._green[index] * remainder
            self._blue[index] = blue * alpha + self._blue[index] * remainder
            self._alpha[index] = alpha + self._alpha[index] * remainder

    def to_bitmap(self) -> Bitmap:
        pixels = bytearray(self._size * self._size * CHANNELS)
        for index, alpha in enumerate(self._alpha):
            target = index * CHANNELS
            if alpha <= 0.0:
                continue
            pixels[target] = _channel(self._red[index] / alpha)
            pixels[target + 1] = _channel(self._green[index] / alpha)
            pixels[target + 2] = _channel(self._blue[index] / alpha)
            pixels[target + 3] = _channel(alpha * OPAQUE)
        return Bitmap(width=self._size, height=self._size, pixels=bytes(pixels))


class _AreaResampler:
    def __init__(self, source: Bitmap) -> None:
        self._source = source

    def to(self, size: int) -> Bitmap:
        step = self._source.width / size
        pixels = bytearray(size * size * CHANNELS)
        for y in range(size):
            for x in range(size):
                self._write(pixels, (y * size + x) * CHANNELS, x, y, step)
        return Bitmap(width=size, height=size, pixels=bytes(pixels))

    def _write(self, pixels: bytearray, target: int, x: int, y: int, step: float) -> None:
        totals = [0.0, 0.0, 0.0, 0.0]
        weight = 0.0
        for source_y in self._span(y, step, self._source.height):
            for source_x in self._span(x, step, self._source.width):
                red, green, blue, alpha = self._source.pixel(source_x, source_y)
                share = alpha / OPAQUE
                totals[0] += red * share
                totals[1] += green * share
                totals[2] += blue * share
                totals[3] += share
                weight += 1.0

        if weight <= 0.0 or totals[3] <= 0.0:
            return
        pixels[target] = _channel(totals[0] / totals[3])
        pixels[target + 1] = _channel(totals[1] / totals[3])
        pixels[target + 2] = _channel(totals[2] / totals[3])
        pixels[target + 3] = _channel(totals[3] / weight * OPAQUE)

    @staticmethod
    def _span(index: int, step: float, limit: int) -> range:
        start = int(index * step)
        end = max(start + 1, int((index + 1) * step))
        return range(start, min(limit, end))


def _channel(value: float) -> int:
    rounded = int(value + 0.5)
    if rounded < 0:
        return 0
    if rounded > OPAQUE:
        return OPAQUE
    return rounded
