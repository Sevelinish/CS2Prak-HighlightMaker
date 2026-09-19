from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Key(Enum):
    CHARACTER = "character"
    ENTER = "enter"
    TAB = "tab"
    BACKSPACE = "backspace"
    DELETE = "delete"
    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"
    HOME = "home"
    END = "end"
    WORD_LEFT = "word_left"
    WORD_RIGHT = "word_right"
    PAGE_UP = "page_up"
    PAGE_DOWN = "page_down"
    DOCUMENT_START = "document_start"
    DOCUMENT_END = "document_end"
    SAVE = "save"
    EXIT = "exit"
    UNDO = "undo"
    REDO = "redo"
    DELETE_WORD = "delete_word"
    DELETE_TO_START = "delete_to_start"
    DELETE_TO_END = "delete_to_end"
    CLEAR_SCREEN = "clear_screen"
    ESCAPE = "escape"
    INTERRUPT = "interrupt"
    END_OF_INPUT = "end_of_input"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class KeyPress:
    key: Key
    character: str = ""

    @property
    def is_character(self) -> bool:
        return self.key is Key.CHARACTER and bool(self.character)

    @classmethod
    def of(cls, character: str) -> "KeyPress":
        return cls(key=Key.CHARACTER, character=character)


CONTROL_KEYS = {
    "\r": Key.ENTER,
    "\n": Key.ENTER,
    "\t": Key.TAB,
    "\x08": Key.BACKSPACE,
    "\x7f": Key.BACKSPACE,
    "\x01": Key.HOME,
    "\x05": Key.END,
    "\x03": Key.INTERRUPT,
    "\x04": Key.END_OF_INPUT,
    "\x0b": Key.DELETE_TO_END,
    "\x0c": Key.CLEAR_SCREEN,
    "\x15": Key.DELETE_TO_START,
    "\x17": Key.DELETE_WORD,
    "\x0f": Key.SAVE,
    "\x13": Key.SAVE,
    "\x18": Key.EXIT,
    "\x19": Key.REDO,
    "\x1a": Key.UNDO,
    "\x1b": Key.ESCAPE,
}

WINDOWS_EXTENDED_KEYS = {
    "H": Key.UP,
    "P": Key.DOWN,
    "K": Key.LEFT,
    "M": Key.RIGHT,
    "G": Key.HOME,
    "O": Key.END,
    "S": Key.DELETE,
    "s": Key.WORD_LEFT,
    "t": Key.WORD_RIGHT,
    "I": Key.PAGE_UP,
    "Q": Key.PAGE_DOWN,
    "w": Key.DOCUMENT_START,
    "u": Key.DOCUMENT_END,
}

ESCAPE_SEQUENCE_KEYS = {
    "[A": Key.UP,
    "[B": Key.DOWN,
    "[C": Key.RIGHT,
    "[D": Key.LEFT,
    "[H": Key.HOME,
    "[F": Key.END,
    "OH": Key.HOME,
    "OF": Key.END,
    "[1~": Key.HOME,
    "[4~": Key.END,
    "[3~": Key.DELETE,
    "[1;5C": Key.WORD_RIGHT,
    "[1;5D": Key.WORD_LEFT,
    "[5~": Key.PAGE_UP,
    "[6~": Key.PAGE_DOWN,
    "[1;5H": Key.DOCUMENT_START,
    "[1;5F": Key.DOCUMENT_END,
}

WINDOWS_EXTENDED_PREFIXES = ("\x00", "\xe0")
SEQUENCE_TERMINATORS = "ABCDFHPQRS~"


class KeyDecoder:
    @staticmethod
    def control(character: str) -> Key | None:
        return CONTROL_KEYS.get(character)

    @staticmethod
    def extended(character: str) -> Key:
        return WINDOWS_EXTENDED_KEYS.get(character, Key.UNKNOWN)

    @staticmethod
    def sequence(body: str) -> Key:
        return ESCAPE_SEQUENCE_KEYS.get(body, Key.UNKNOWN)

    @staticmethod
    def is_complete_sequence(body: str) -> bool:
        if not body:
            return False
        if body[0] not in "[O":
            return True
        if len(body) < 2:
            return False
        return body[-1] in SEQUENCE_TERMINATORS
