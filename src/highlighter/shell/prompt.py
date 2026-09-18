from __future__ import annotations

from dataclasses import dataclass

from .context import LineContext
from .document import Document
from .grammar import Candidate
from .history import CommandHistory
from .keys import Key, KeyPress
from .reader import KeyReader
from .renderer import LineRenderer
from .suggester import Suggester, Suggestion


@dataclass(frozen=True, slots=True)
class Submission:
    line: str | None = None


@dataclass(frozen=True, slots=True)
class Stem:
    start: int
    text: str


EDITS = {
    Key.BACKSPACE: Document.backspace,
    Key.DELETE: Document.delete,
    Key.DELETE_WORD: Document.delete_word_before,
    Key.DELETE_TO_START: Document.delete_to_start,
    Key.DELETE_TO_END: Document.delete_to_end,
    Key.LEFT: Document.move_left,
    Key.HOME: Document.move_home,
    Key.WORD_LEFT: Document.move_word_left,
    Key.WORD_RIGHT: Document.move_word_right,
    Key.ESCAPE: Document.cleared,
}


class LinePrompt:
    def __init__(
        self,
        reader: KeyReader,
        renderer: LineRenderer,
        suggester: Suggester,
        history: CommandHistory | None = None,
    ) -> None:
        self._reader = reader
        self._renderer = renderer
        self._suggester = suggester
        self._history = history or CommandHistory()
        self._document = Document()
        self._stem: Stem | None = None
        self._rotation = 0

    def read(self) -> str | None:
        self._document = Document()
        self._forget_stem()
        self._history.reset()

        while True:
            suggestion = self._suggester.suggest(self._document)
            self._renderer.render(self._document, suggestion)
            submission = self._apply(self._reader.read(), suggestion)
            if submission is not None:
                return submission.line

    def _apply(self, press: KeyPress, suggestion: Suggestion) -> Submission | None:
        if press.key is not Key.TAB:
            self._forget_stem()

        if press.is_character:
            self._document = self._document.insert(press.character)
            return None

        handler = getattr(self, f"_on_{press.key.value}", None)
        if handler is not None:
            return handler(suggestion)

        edit = EDITS.get(press.key)
        if edit is not None:
            self._document = edit(self._document)
        return None

    def _on_enter(self, suggestion: Suggestion) -> Submission:
        self._renderer.settle(self._document)
        return Submission(self._document.text)

    def _on_interrupt(self, suggestion: Suggestion) -> Submission | None:
        if not self._document.text:
            self._renderer.settle(self._document)
            return Submission(None)
        self._document = self._document.cleared()
        return None

    def _on_end_of_input(self, suggestion: Suggestion) -> Submission:
        self._renderer.settle(self._document)
        return Submission(None)

    def _on_right(self, suggestion: Suggestion) -> None:
        if self._document.at_end and suggestion.has_completion:
            self._document = self._document.insert(suggestion.completion)
            return None
        self._document = self._document.move_right()
        return None

    def _on_end(self, suggestion: Suggestion) -> None:
        if self._document.at_end and suggestion.has_completion:
            self._document = self._document.insert(suggestion.completion)
            return None
        self._document = self._document.move_end()
        return None

    def _on_tab(self, suggestion: Suggestion) -> None:
        candidates = self._rotating_candidates()
        if not candidates:
            if suggestion.has_completion:
                self._document = self._document.insert(suggestion.completion)
            self._forget_stem()
            return None

        stem = self._stem
        chosen = candidates[self._rotation % len(candidates)]
        self._rotation += 1
        self._document = self._document.replace_range(
            stem.start, self._document.cursor, chosen.text
        )
        return None

    def _on_up(self, suggestion: Suggestion) -> None:
        self._recall(self._history.previous(self._document.text))
        return None

    def _on_down(self, suggestion: Suggestion) -> None:
        self._recall(self._history.following())
        return None

    def _on_clear_screen(self, suggestion: Suggestion) -> None:
        self._renderer.clear_screen()
        return None

    def _recall(self, line: str | None) -> None:
        if line is None:
            return
        self._document = self._document.with_text(line)

    def _rotating_candidates(self) -> tuple[Candidate, ...]:
        if self._stem is None:
            context = LineContext.of(self._document)
            self._stem = Stem(start=context.word_start, text=context.word)
            self._rotation = 0
        return self._suggester.candidates(self._probe())

    def _probe(self) -> Document:
        stem = self._stem
        head = self._document.text[: stem.start] + stem.text
        return Document(text=head + self._document.after_cursor, cursor=len(head))

    def _forget_stem(self) -> None:
        self._stem = None
        self._rotation = 0
