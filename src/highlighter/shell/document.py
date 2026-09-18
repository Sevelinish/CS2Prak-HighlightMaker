from __future__ import annotations

from dataclasses import dataclass

WORD_SEPARATORS = " \t"


@dataclass(frozen=True, slots=True)
class Document:
    text: str = ""
    cursor: int = 0

    @property
    def at_end(self) -> bool:
        return self.cursor >= len(self.text)

    @property
    def before_cursor(self) -> str:
        return self.text[: self.cursor]

    @property
    def after_cursor(self) -> str:
        return self.text[self.cursor :]

    def insert(self, value: str) -> "Document":
        return Document(
            text=self.before_cursor + value + self.after_cursor,
            cursor=self.cursor + len(value),
        )

    def replace_range(self, start: int, end: int, value: str) -> "Document":
        head = self.text[: max(0, start)]
        tail = self.text[max(0, end) :]
        return Document(text=head + value + tail, cursor=len(head) + len(value))

    def with_text(self, value: str) -> "Document":
        return Document(text=value, cursor=len(value))

    def cleared(self) -> "Document":
        return Document()

    def backspace(self) -> "Document":
        if self.cursor == 0:
            return self
        return Document(
            text=self.text[: self.cursor - 1] + self.after_cursor,
            cursor=self.cursor - 1,
        )

    def delete(self) -> "Document":
        if self.at_end:
            return self
        return Document(
            text=self.before_cursor + self.text[self.cursor + 1 :], cursor=self.cursor
        )

    def delete_word_before(self) -> "Document":
        start = self._word_start()
        if start == self.cursor:
            return self
        return Document(text=self.text[:start] + self.after_cursor, cursor=start)

    def delete_to_start(self) -> "Document":
        return Document(text=self.after_cursor, cursor=0)

    def delete_to_end(self) -> "Document":
        return Document(text=self.before_cursor, cursor=self.cursor)

    def move_left(self) -> "Document":
        return Document(text=self.text, cursor=max(0, self.cursor - 1))

    def move_right(self) -> "Document":
        return Document(text=self.text, cursor=min(len(self.text), self.cursor + 1))

    def move_home(self) -> "Document":
        return Document(text=self.text, cursor=0)

    def move_end(self) -> "Document":
        return Document(text=self.text, cursor=len(self.text))

    def move_word_left(self) -> "Document":
        return Document(text=self.text, cursor=self._word_start())

    def move_word_right(self) -> "Document":
        return Document(text=self.text, cursor=self._word_end())

    def _word_start(self) -> int:
        index = self.cursor
        while index > 0 and self.text[index - 1] in WORD_SEPARATORS:
            index -= 1
        while index > 0 and self.text[index - 1] not in WORD_SEPARATORS:
            index -= 1
        return index

    def _word_end(self) -> int:
        index = self.cursor
        length = len(self.text)
        while index < length and self.text[index] in WORD_SEPARATORS:
            index += 1
        while index < length and self.text[index] not in WORD_SEPARATORS:
            index += 1
        return index
