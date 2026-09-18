from __future__ import annotations

from dataclasses import dataclass

from .document import Document
from .suggester import Suggestion

HINT_GAP = "   "
MINIMUM_HINT_WIDTH = 8
RESERVED_COLUMN = 1


@dataclass(frozen=True, slots=True)
class RenderedLine:
    prompt: str = ""
    text: str = ""
    ghost: str = ""
    hint: str = ""
    cursor_column: int = 0


class LineLayout:
    def __init__(self, prompt: str, width: int, gap: str = HINT_GAP) -> None:
        self._prompt = prompt
        self._width = width
        self._gap = gap

    def build(self, document: Document, suggestion: Suggestion) -> RenderedLine:
        budget = max(len(self._prompt) + MINIMUM_HINT_WIDTH, self._width - RESERVED_COLUMN)
        room = budget - len(self._prompt)
        offset = max(0, document.cursor - room + RESERVED_COLUMN)
        text = document.text[offset : offset + room]

        used = len(self._prompt) + len(text)
        ghost = self._ghost(document, suggestion, offset, budget - used)
        used += len(ghost)

        return RenderedLine(
            prompt=self._prompt,
            text=text,
            ghost=ghost,
            hint=self._hint(suggestion, budget - used),
            cursor_column=len(self._prompt) + document.cursor - offset,
        )

    @staticmethod
    def _ghost(
        document: Document, suggestion: Suggestion, offset: int, room: int
    ) -> str:
        if offset > 0 or not document.at_end or room <= 0:
            return ""
        return suggestion.ghost[:room]

    def _hint(self, suggestion: Suggestion, room: int) -> str:
        if not suggestion.hint:
            return ""
        available = room - len(self._gap)
        if available < MINIMUM_HINT_WIDTH:
            return ""
        return f"{self._gap}{suggestion.hint[:available]}"
