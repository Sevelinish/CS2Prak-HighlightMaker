from __future__ import annotations

from .buffer import TextBuffer

DEFAULT_DEPTH = 200


class EditHistory:
    def __init__(self, start: TextBuffer, depth: int = DEFAULT_DEPTH) -> None:
        self._depth = max(1, depth)
        self._done: list[TextBuffer] = [start]
        self._undone: list[TextBuffer] = []

    @property
    def can_undo(self) -> bool:
        return len(self._done) > 1

    @property
    def can_redo(self) -> bool:
        return bool(self._undone)

    def record(self, buffer: TextBuffer) -> None:
        if buffer.lines == self._done[-1].lines:
            self._done[-1] = buffer
            return
        self._done.append(buffer)
        del self._done[: max(0, len(self._done) - self._depth)]
        self._undone.clear()

    def undo(self, current: TextBuffer) -> TextBuffer:
        if not self.can_undo:
            return current
        self._undone.append(self._done.pop())
        return self._done[-1]

    def redo(self, current: TextBuffer) -> TextBuffer:
        if not self.can_redo:
            return current
        restored = self._undone.pop()
        self._done.append(restored)
        return restored
