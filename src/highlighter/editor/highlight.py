from __future__ import annotations

import re
from dataclasses import dataclass

from .theme import Ink

STRING_PATTERN = re.compile(r'"(?:[^"\\]|\\.)*"?')
NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
LITERAL_PATTERN = re.compile(r"true|false|null")
PUNCTUATION = set("{}[],:")
KEY_FOLLOWER = ":"


@dataclass(frozen=True, slots=True)
class Span:
    text: str
    ink: Ink


class JsonHighlighter:
    def spans(self, line: str) -> tuple[Span, ...]:
        found: list[Span] = []
        index = 0
        plain = ""

        while index < len(line):
            span, length = self._at(line, index)
            if span is None:
                plain += line[index]
                index += 1
                continue
            if plain:
                found.append(Span(plain, Ink.PLAIN))
                plain = ""
            found.append(span)
            index += length

        if plain:
            found.append(Span(plain, Ink.PLAIN))
        return tuple(found)

    def _at(self, line: str, index: int) -> tuple[Span | None, int]:
        character = line[index]
        if character in PUNCTUATION:
            return Span(character, Ink.PUNCTUATION), 1

        if character == '"':
            match = STRING_PATTERN.match(line, index)
            if match is not None:
                return Span(match.group(), self._string_ink(line, match.end())), len(
                    match.group()
                )

        if character.isdigit() or (character == "-" and self._starts_number(line, index)):
            match = NUMBER_PATTERN.match(line, index)
            if match is not None:
                return Span(match.group(), Ink.NUMBER), len(match.group())

        match = LITERAL_PATTERN.match(line, index)
        if match is not None:
            return Span(match.group(), Ink.LITERAL), len(match.group())
        return None, 0

    @staticmethod
    def _string_ink(line: str, end: int) -> Ink:
        rest = line[end:].lstrip()
        return Ink.KEY if rest.startswith(KEY_FOLLOWER) else Ink.STRING

    @staticmethod
    def _starts_number(line: str, index: int) -> bool:
        return index + 1 < len(line) and line[index + 1].isdigit()
