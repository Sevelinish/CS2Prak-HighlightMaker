from __future__ import annotations

from .document import Document
from .layout import LineLayout, RenderedLine
from .suggester import Suggestion
from .terminal import (
    CARRIAGE_RETURN,
    CLEAR_SCREEN,
    ERASE_LINE,
    GHOST_STYLE,
    HINT_STYLE,
    NEWLINE,
    PROMPT_STYLE,
    RESET,
    Terminal,
)


class LineRenderer:
    def __init__(self, prompt: str, terminal: Terminal | None = None) -> None:
        self._prompt = prompt
        self._terminal = terminal or Terminal()

    def layout(self, document: Document, suggestion: Suggestion) -> RenderedLine:
        return LineLayout(self._prompt, self._terminal.width).build(document, suggestion)

    def render(self, document: Document, suggestion: Suggestion) -> None:
        line = self.layout(document, suggestion)
        self._terminal.write(
            f"{CARRIAGE_RETURN}{ERASE_LINE}"
            f"{PROMPT_STYLE}{line.prompt}{RESET}{line.text}"
            f"{GHOST_STYLE}{line.ghost}{RESET}"
            f"{HINT_STYLE}{line.hint}{RESET}"
            f"{self._terminal.column(line.cursor_column)}"
        )
        self._terminal.flush()

    def settle(self, document: Document) -> None:
        self._terminal.write(
            f"{CARRIAGE_RETURN}{ERASE_LINE}"
            f"{PROMPT_STYLE}{self._prompt}{RESET}{document.text}{NEWLINE}"
        )
        self._terminal.flush()

    def clear_screen(self) -> None:
        self._terminal.write(CLEAR_SCREEN)
        self._terminal.flush()
