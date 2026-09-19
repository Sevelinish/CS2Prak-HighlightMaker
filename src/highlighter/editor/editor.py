from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..shell.keys import Key, KeyPress
from ..shell.reader import KeyReader
from .buffer import INDENT, TextBuffer
from .history import EditHistory
from .screen import EditorScreen, Status
from .theme import Ink
from .validator import JsonValidator, Verdict
from .viewport import Viewport

OPENING_MESSAGE = "Ctrl+S saves, Ctrl+X leaves"
SAVED_MESSAGE = "written to disk"
NOTHING_TO_SAVE = "nothing changed"
LEAVE_QUESTION = "Save before leaving?  y  save    n  throw away    Esc  keep editing"
UNCHANGED_MESSAGE = "left without changes"
DISCARDED_MESSAGE = "left, the file on disk was not touched"
YES = "y"
NO = "n"

MOVES = {
    Key.LEFT: TextBuffer.move_left,
    Key.RIGHT: TextBuffer.move_right,
    Key.UP: TextBuffer.move_up,
    Key.DOWN: TextBuffer.move_down,
    Key.HOME: TextBuffer.move_home,
    Key.END: TextBuffer.move_end,
    Key.WORD_LEFT: TextBuffer.move_word_left,
    Key.WORD_RIGHT: TextBuffer.move_word_right,
    Key.DOCUMENT_START: TextBuffer.move_to_start,
    Key.DOCUMENT_END: TextBuffer.move_to_end,
}

EDITS = {
    Key.ENTER: TextBuffer.split_line,
    Key.BACKSPACE: TextBuffer.backspace,
    Key.DELETE: TextBuffer.delete,
    Key.DELETE_WORD: TextBuffer.delete_word_before,
    Key.DELETE_TO_END: TextBuffer.delete_to_end,
}

LEAVING_KEYS = (Key.EXIT, Key.ESCAPE, Key.INTERRUPT, Key.END_OF_INPUT)


@dataclass(frozen=True, slots=True)
class EditorOutcome:
    text: str = ""
    saved: bool = False


class TextEditor:
    def __init__(
        self,
        reader: KeyReader,
        screen: EditorScreen,
        title: str = "",
        validator: JsonValidator | None = None,
        writer: Callable[[str], None] | None = None,
    ) -> None:
        self._reader = reader
        self._screen = screen
        self._title = title
        self._validator = validator
        self._writer = writer
        self._buffer = TextBuffer()
        self._history = EditHistory(self._buffer)
        self._viewport = Viewport()
        self._modified = False
        self._saved = False
        self._message = OPENING_MESSAGE
        self._ink = Ink.BAR_QUIET

    def edit(self, text: str) -> EditorOutcome:
        self._start(text)
        self._screen.open()
        try:
            return self._loop()
        finally:
            self._screen.close()

    def _start(self, text: str) -> None:
        self._buffer = TextBuffer.of(text)
        self._history = EditHistory(self._buffer)
        self._viewport = Viewport()
        self._modified = False
        self._saved = False
        self._message = OPENING_MESSAGE
        self._ink = Ink.BAR_QUIET

    def _loop(self) -> EditorOutcome:
        while True:
            self._paint()
            outcome = self._apply(self._reader.read())
            if outcome is not None:
                return outcome

    def _paint(self) -> None:
        self._viewport = self._screen.fitted(self._viewport, self._buffer)
        self._screen.draw(self._buffer, self._viewport, self._status())

    def _status(self) -> Status:
        return Status(
            title=self._title,
            modified=self._modified,
            message=self._message,
            ink=self._ink,
        )

    def _apply(self, press: KeyPress) -> EditorOutcome | None:
        if press.is_character:
            return self._changed(self._buffer.insert(press.character))

        if press.key in LEAVING_KEYS:
            return self._leave()
        if press.key is Key.SAVE:
            self._save()
            return None
        if press.key is Key.TAB:
            return self._changed(self._buffer.insert(INDENT))
        if press.key is Key.UNDO:
            return self._rewind(self._history.undo(self._buffer))
        if press.key is Key.REDO:
            return self._rewind(self._history.redo(self._buffer))
        if press.key is Key.PAGE_UP:
            self._buffer = self._buffer.move_page_up(self._viewport.rows)
            return None
        if press.key is Key.PAGE_DOWN:
            self._buffer = self._buffer.move_page_down(self._viewport.rows)
            return None

        move = MOVES.get(press.key)
        if move is not None:
            self._buffer = move(self._buffer)
            return None

        edit = EDITS.get(press.key)
        if edit is not None:
            return self._changed(edit(self._buffer))
        return None

    def _changed(self, buffer: TextBuffer) -> None:
        if buffer.lines != self._buffer.lines:
            self._modified = True
            self._note(OPENING_MESSAGE, Ink.BAR_QUIET)
        self._buffer = buffer
        self._history.record(buffer)
        return None

    def _rewind(self, buffer: TextBuffer) -> None:
        self._buffer = buffer
        self._modified = True
        return None

    def _save(self) -> None:
        verdict = self._verdict()
        if not verdict.ok:
            self._buffer = self._buffer.move_to(verdict.row, verdict.column)
            self._note(verdict.message, Ink.WARNING)
            return

        if not self._modified:
            self._note(NOTHING_TO_SAVE, Ink.BAR_QUIET)
            return

        try:
            self._write()
        except OSError as error:
            self._note(f"could not write the file: {error}", Ink.WARNING)
            return

        self._modified = False
        self._saved = True
        self._note(SAVED_MESSAGE, Ink.GOOD)

    def _verdict(self) -> Verdict:
        if self._validator is None:
            return Verdict.fine()
        return self._validator.check(self._buffer.text)

    def _write(self) -> None:
        if self._writer is not None:
            self._writer(self._buffer.text)

    def _leave(self) -> EditorOutcome | None:
        if not self._modified:
            return self._done(UNCHANGED_MESSAGE)

        answer = self._ask()
        if answer == YES:
            self._save()
            if self._modified:
                return None
            return self._done(SAVED_MESSAGE)
        if answer == NO:
            return self._done(DISCARDED_MESSAGE)
        self._note(OPENING_MESSAGE, Ink.BAR_QUIET)
        return None

    def _ask(self) -> str:
        self._note(LEAVE_QUESTION, Ink.WARNING)
        self._paint()
        press = self._reader.read()
        return press.character.lower() if press.is_character else ""

    def _done(self, message: str) -> EditorOutcome:
        self._note(message, Ink.BAR_QUIET)
        return EditorOutcome(text=self._buffer.text, saved=self._saved)

    def _note(self, message: str, ink: Ink) -> None:
        self._message = message
        self._ink = ink
