from __future__ import annotations

from dataclasses import dataclass

from .document import Document
from .tokens import Lexer, Token


@dataclass(frozen=True, slots=True)
class LineContext:
    tokens: tuple[Token, ...] = ()
    word: str = ""
    word_start: int = 0
    word_end: int = 0
    preceding: str = ""
    position: int = 0

    @property
    def is_first_word(self) -> bool:
        return self.position == 0

    @property
    def word_is_flag(self) -> bool:
        return self.word.startswith("-")

    def other_flags(self) -> tuple[str, ...]:
        return tuple(
            token.text
            for token in self.tokens
            if token.is_flag and token.start != self.word_start
        )

    @classmethod
    def of(cls, document: Document) -> "LineContext":
        tokens = Lexer.split(document.text)
        typed = Lexer.split(document.before_cursor)
        if cls._starts_new_word(document):
            return cls(
                tokens=tokens,
                word="",
                word_start=document.cursor,
                word_end=document.cursor,
                preceding=typed[-1].text if typed else "",
                position=len(typed),
            )

        active = typed[-1]
        return cls(
            tokens=tokens,
            word=active.text,
            word_start=active.start,
            word_end=document.cursor,
            preceding=typed[-2].text if len(typed) > 1 else "",
            position=len(typed) - 1,
        )

    @staticmethod
    def _starts_new_word(document: Document) -> bool:
        if document.cursor == 0:
            return True
        return document.text[document.cursor - 1].isspace()
