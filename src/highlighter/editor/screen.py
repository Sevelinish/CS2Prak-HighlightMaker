from __future__ import annotations

from dataclasses import dataclass

from ..shell.terminal import (
    CLEAR_SCREEN,
    ENTER_FULL_SCREEN,
    ERASE_LINE,
    HIDE_CURSOR,
    LEAVE_FULL_SCREEN,
    SHOW_CURSOR,
    Terminal,
)
from .buffer import TextBuffer
from .highlight import JsonHighlighter
from .theme import Ink, Palette
from .viewport import Viewport

GUTTER_SEPARATOR = " | "
BAR_ROWS = 3
TITLE_ROW = 1
FIRST_TEXT_ROW = 2
MODIFIED_MARK = "modified"
SAVED_MARK = "saved"
HELP = "Ctrl+S save   Ctrl+X leave   Ctrl+Z undo   Ctrl+Y redo   Ctrl+K cut to end"


@dataclass(frozen=True, slots=True)
class Status:
    title: str = ""
    modified: bool = False
    message: str = ""
    ink: Ink = Ink.BAR_QUIET


class EditorScreen:
    def __init__(
        self,
        terminal: Terminal | None = None,
        palette: Palette | None = None,
        highlighter: JsonHighlighter | None = None,
    ) -> None:
        self._terminal = terminal or Terminal()
        self._palette = palette or Palette()
        self._highlighter = highlighter or JsonHighlighter()

    @property
    def terminal(self) -> Terminal:
        return self._terminal

    def open(self) -> None:
        self._terminal.write(f"{ENTER_FULL_SCREEN}{CLEAR_SCREEN}")
        self._terminal.flush()

    def close(self) -> None:
        self._terminal.write(f"{SHOW_CURSOR}{LEAVE_FULL_SCREEN}")
        self._terminal.flush()

    def draw(self, buffer: TextBuffer, viewport: Viewport, status: Status) -> None:
        self._terminal.write(self.render(buffer, viewport, status))
        self._terminal.flush()

    def fitted(self, viewport: Viewport, buffer: TextBuffer) -> Viewport:
        return viewport.resized(
            rows=self._terminal.height - BAR_ROWS,
            columns=self._terminal.width - self._gutter_width(buffer),
        ).following(buffer)

    def render(self, buffer: TextBuffer, viewport: Viewport, status: Status) -> str:
        width = self._terminal.width
        height = self._terminal.height
        gutter = self._gutter_width(buffer)

        frame = [HIDE_CURSOR, self._terminal.position(TITLE_ROW, 1), ERASE_LINE]
        frame.append(self._title(status, width))
        frame.extend(self._body(buffer, viewport, gutter))
        frame.append(self._terminal.position(height - 1, 1))
        frame.append(ERASE_LINE)
        frame.append(self._message(buffer, status, width))
        frame.append(self._terminal.position(height, 1))
        frame.append(ERASE_LINE)
        frame.append(self._palette.paint(Ink.BAR_QUIET, HELP[: width - 1]))
        frame.append(
            self._terminal.position(
                FIRST_TEXT_ROW + viewport.screen_row(buffer.row),
                gutter + 1 + viewport.screen_column(buffer.column),
            )
        )
        frame.append(SHOW_CURSOR)
        return "".join(frame)

    def _body(self, buffer: TextBuffer, viewport: Viewport, gutter: int) -> list[str]:
        drawn: list[str] = []
        rows = viewport.rows
        numbers = tuple(viewport.visible_rows(buffer))

        for offset in range(rows):
            drawn.append(self._terminal.position(FIRST_TEXT_ROW + offset, 1))
            drawn.append(ERASE_LINE)
            if offset >= len(numbers):
                continue
            row = numbers[offset]
            drawn.append(self._gutter(row, buffer.row, gutter))
            drawn.append(self._painted(buffer.line_at(row), viewport))
        return drawn

    def _gutter(self, row: int, current: int, width: int) -> str:
        label = f"{row + 1:>{width - len(GUTTER_SEPARATOR)}}{GUTTER_SEPARATOR}"
        ink = Ink.CURRENT_GUTTER if row == current else Ink.GUTTER
        return self._palette.paint(ink, label)

    def _painted(self, line: str, viewport: Viewport) -> str:
        start = viewport.left
        end = start + viewport.columns
        pieces: list[str] = []
        position = 0

        for span in self._highlighter.spans(line):
            finish = position + len(span.text)
            if finish > start and position < end:
                piece = span.text[max(0, start - position) : max(0, end - position)]
                pieces.append(self._palette.paint(span.ink, piece))
            position = finish
        return "".join(pieces)

    def _title(self, status: Status, width: int) -> str:
        mark = MODIFIED_MARK if status.modified else SAVED_MARK
        room = max(0, width - len(mark) - 2)
        left = f" {status.title}"[:room]
        line = f"{left}{' ' * (room - len(left))} {mark} "
        return self._palette.paint(Ink.BAR, line[:width])

    def _message(self, buffer: TextBuffer, status: Status, width: int) -> str:
        where = f"line {buffer.row + 1}, column {buffer.column + 1}"
        room = max(0, width - len(where) - 2)
        body = f" {status.message}"[:room]
        painted = self._palette.paint(status.ink, body)
        return f"{painted}{' ' * (room - len(body))} {where} "

    @staticmethod
    def _gutter_width(buffer: TextBuffer) -> int:
        return len(str(buffer.line_count)) + len(GUTTER_SEPARATOR)
