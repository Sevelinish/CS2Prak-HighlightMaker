from __future__ import annotations

from dataclasses import dataclass

QUOTE_CHARACTERS = ('"', "'")
FLAG_PREFIX = "-"


@dataclass(frozen=True, slots=True)
class Token:
    text: str
    start: int
    end: int

    @property
    def is_flag(self) -> bool:
        return len(self.text) > 1 and self.text.startswith(FLAG_PREFIX)


class Lexer:
    @classmethod
    def split(cls, line: str) -> tuple[Token, ...]:
        tokens: list[Token] = []
        index = 0
        while index < len(line):
            if line[index].isspace():
                index += 1
                continue
            token, index = cls._read(line, index)
            tokens.append(token)
        return tuple(tokens)

    @classmethod
    def argv(cls, line: str) -> list[str]:
        return [token.text for token in cls.split(line)]

    @staticmethod
    def _read(line: str, start: int) -> tuple[Token, int]:
        collected: list[str] = []
        quote = ""
        index = start

        while index < len(line):
            character = line[index]
            if quote:
                if character == quote:
                    quote = ""
                else:
                    collected.append(character)
            elif character in QUOTE_CHARACTERS:
                quote = character
            elif character.isspace():
                break
            else:
                collected.append(character)
            index += 1

        return Token(text="".join(collected), start=start, end=index), index
