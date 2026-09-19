from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

WORD_SEPARATORS = " \t{}[]:,\"'"
INDENT = "  "


@dataclass(frozen=True, slots=True)
class TextBuffer:
    lines: tuple[str, ...] = ("",)
    row: int = 0
    column: int = 0
    wanted_column: int = 0

    @classmethod
    def of(cls, text: str) -> "TextBuffer":
        lines = text.replace("\t", INDENT).split("\n")
        return cls(lines=tuple(lines) if lines else ("",))

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    @property
    def line_count(self) -> int:
        return len(self.lines)

    @property
    def line(self) -> str:
        return self.lines[self.row]

    @property
    def at_last_line(self) -> bool:
        return self.row >= self.line_count - 1

    def line_at(self, index: int) -> str:
        if 0 <= index < self.line_count:
            return self.lines[index]
        return ""

    def insert(self, value: str) -> "TextBuffer":
        line = self.line
        head, tail = line[: self.column], line[self.column :]
        return self._with_lines(
            self._replaced(self.row, head + value + tail),
            self.row,
            self.column + len(value),
        )

    def split_line(self) -> "TextBuffer":
        line = self.line
        head, tail = line[: self.column], line[self.column :]
        indent = self._indent_of(line)
        lines = (
            *self.lines[: self.row],
            head,
            indent + tail,
            *self.lines[self.row + 1 :],
        )
        return self._with_lines(lines, self.row + 1, len(indent))

    def backspace(self) -> "TextBuffer":
        if self.column > 0:
            width = self._outdent_width()
            line = self.line
            return self._with_lines(
                self._replaced(self.row, line[: self.column - width] + line[self.column :]),
                self.row,
                self.column - width,
            )
        if self.row == 0:
            return self
        return self._join(self.row - 1)

    def delete(self) -> "TextBuffer":
        line = self.line
        if self.column < len(line):
            return self._with_lines(
                self._replaced(self.row, line[: self.column] + line[self.column + 1 :]),
                self.row,
                self.column,
            )
        if self.at_last_line:
            return self
        return self._join(self.row)

    def delete_to_end(self) -> "TextBuffer":
        line = self.line
        if self.column < len(line):
            return self._with_lines(
                self._replaced(self.row, line[: self.column]), self.row, self.column
            )
        if self.at_last_line:
            return self
        return self._join(self.row)

    def delete_word_before(self) -> "TextBuffer":
        if self.column == 0:
            return self.backspace()
        start = self._word_start()
        line = self.line
        return self._with_lines(
            self._replaced(self.row, line[:start] + line[self.column :]), self.row, start
        )

    def move_left(self) -> "TextBuffer":
        if self.column > 0:
            return self._moved(self.row, self.column - 1)
        if self.row == 0:
            return self
        return self._moved(self.row - 1, len(self.line_at(self.row - 1)))

    def move_right(self) -> "TextBuffer":
        if self.column < len(self.line):
            return self._moved(self.row, self.column + 1)
        if self.at_last_line:
            return self
        return self._moved(self.row + 1, 0)

    def move_up(self) -> "TextBuffer":
        return self._vertical(-1)

    def move_down(self) -> "TextBuffer":
        return self._vertical(1)

    def move_page_up(self, rows: int) -> "TextBuffer":
        return self._vertical(-max(1, rows))

    def move_page_down(self, rows: int) -> "TextBuffer":
        return self._vertical(max(1, rows))

    def move_home(self) -> "TextBuffer":
        return self._moved(self.row, self._first_column())

    def move_end(self) -> "TextBuffer":
        return self._moved(self.row, len(self.line))

    def move_word_left(self) -> "TextBuffer":
        if self.column == 0:
            return self.move_left()
        return self._moved(self.row, self._word_start())

    def move_word_right(self) -> "TextBuffer":
        if self.column >= len(self.line):
            return self.move_right()
        return self._moved(self.row, self._word_end())

    def move_to_start(self) -> "TextBuffer":
        return self._moved(0, 0)

    def move_to_end(self) -> "TextBuffer":
        last = self.line_count - 1
        return self._moved(last, len(self.line_at(last)))

    def move_to(self, row: int, column: int = 0) -> "TextBuffer":
        return self._moved(row, column)

    def _vertical(self, step: int) -> "TextBuffer":
        row = min(max(0, self.row + step), self.line_count - 1)
        if row == self.row:
            return self
        wanted = max(self.wanted_column, self.column)
        return replace(
            self,
            row=row,
            column=min(wanted, len(self.line_at(row))),
            wanted_column=wanted,
        )

    def _join(self, row: int) -> "TextBuffer":
        merged = self.line_at(row) + self.line_at(row + 1)
        lines = (*self.lines[:row], merged, *self.lines[row + 2 :])
        return self._with_lines(lines, row, len(self.line_at(row)))

    def _replaced(self, row: int, value: str) -> tuple[str, ...]:
        return (*self.lines[:row], value, *self.lines[row + 1 :])

    def _with_lines(
        self, lines: Sequence[str], row: int, column: int
    ) -> "TextBuffer":
        safe = tuple(lines) if lines else ("",)
        row = min(max(0, row), len(safe) - 1)
        return TextBuffer(
            lines=safe,
            row=row,
            column=min(max(0, column), len(safe[row])),
            wanted_column=0,
        )

    def _moved(self, row: int, column: int) -> "TextBuffer":
        row = min(max(0, row), self.line_count - 1)
        return replace(
            self,
            row=row,
            column=min(max(0, column), len(self.line_at(row))),
            wanted_column=0,
        )

    def _first_column(self) -> int:
        indent = len(self._indent_of(self.line))
        return 0 if self.column == indent else indent

    def _outdent_width(self) -> int:
        head = self.line[: self.column]
        if head and not head.strip() and self.column % len(INDENT) == 0:
            return len(INDENT)
        return 1

    def _word_start(self) -> int:
        index = self.column
        line = self.line
        while index > 0 and line[index - 1] in WORD_SEPARATORS:
            index -= 1
        while index > 0 and line[index - 1] not in WORD_SEPARATORS:
            index -= 1
        return index

    def _word_end(self) -> int:
        index = self.column
        line = self.line
        while index < len(line) and line[index] in WORD_SEPARATORS:
            index += 1
        while index < len(line) and line[index] not in WORD_SEPARATORS:
            index += 1
        return index

    @staticmethod
    def _indent_of(line: str) -> str:
        return line[: len(line) - len(line.lstrip(" "))]
