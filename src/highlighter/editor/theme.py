from __future__ import annotations

from enum import Enum

from ..shell.terminal import CSI, RESET


class Ink(Enum):
    PLAIN = "plain"
    KEY = "key"
    STRING = "string"
    NUMBER = "number"
    LITERAL = "literal"
    PUNCTUATION = "punctuation"
    GUTTER = "gutter"
    CURRENT_GUTTER = "current_gutter"
    BAR = "bar"
    BAR_QUIET = "bar_quiet"
    WARNING = "warning"
    GOOD = "good"


STYLES = {
    Ink.PLAIN: "",
    Ink.KEY: f"{CSI}38;5;81m",
    Ink.STRING: f"{CSI}38;5;114m",
    Ink.NUMBER: f"{CSI}38;5;215m",
    Ink.LITERAL: f"{CSI}38;5;176m",
    Ink.PUNCTUATION: f"{CSI}38;5;245m",
    Ink.GUTTER: f"{CSI}38;5;239m",
    Ink.CURRENT_GUTTER: f"{CSI}38;5;250m",
    Ink.BAR: f"{CSI}7m",
    Ink.BAR_QUIET: f"{CSI}38;5;244m",
    Ink.WARNING: f"{CSI}1;38;5;203m",
    Ink.GOOD: f"{CSI}1;38;5;114m",
}


class Palette:
    def __init__(self, coloured: bool = True) -> None:
        self._coloured = coloured

    def paint(self, ink: Ink, text: str) -> str:
        style = STYLES.get(ink, "") if self._coloured else ""
        if not style or not text:
            return text
        return f"{style}{text}{RESET}"
