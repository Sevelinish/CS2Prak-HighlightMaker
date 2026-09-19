from __future__ import annotations

from dataclasses import dataclass

from .buffer import TextBuffer

SCROLL_MARGIN = 1


@dataclass(frozen=True, slots=True)
class Viewport:
    top: int = 0
    left: int = 0
    rows: int = 20
    columns: int = 80

    @property
    def bottom(self) -> int:
        return self.top + self.rows - 1

    def visible_rows(self, buffer: TextBuffer) -> range:
        return range(self.top, min(self.top + self.rows, buffer.line_count))

    def slice_of(self, line: str) -> str:
        return line[self.left : self.left + self.columns]

    def screen_row(self, row: int) -> int:
        return row - self.top

    def screen_column(self, column: int) -> int:
        return column - self.left

    def resized(self, rows: int, columns: int) -> "Viewport":
        return Viewport(top=self.top, left=self.left, rows=max(1, rows), columns=max(1, columns))

    def following(self, buffer: TextBuffer) -> "Viewport":
        return Viewport(
            top=self._vertical(buffer),
            left=self._horizontal(buffer),
            rows=self.rows,
            columns=self.columns,
        )

    def _vertical(self, buffer: TextBuffer) -> int:
        top = self.top
        if buffer.row < top:
            top = buffer.row
        elif buffer.row > top + self.rows - 1:
            top = buffer.row - self.rows + 1
        highest = max(0, buffer.line_count - self.rows)
        return min(max(0, top), highest)

    def _horizontal(self, buffer: TextBuffer) -> int:
        left = self.left
        if buffer.column < left:
            left = buffer.column
        elif buffer.column > left + self.columns - SCROLL_MARGIN - 1:
            left = buffer.column - self.columns + SCROLL_MARGIN + 1
        return max(0, left)
