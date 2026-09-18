from __future__ import annotations

import sys
from typing import Protocol

from .keys import Key, KeyDecoder, KeyPress, WINDOWS_EXTENDED_PREFIXES

MAXIMUM_SEQUENCE_LENGTH = 8


class KeyReader(Protocol):
    def read(self) -> KeyPress: ...


class WindowsKeyReader:
    def __init__(self, source=None) -> None:
        import msvcrt

        self._source = source or msvcrt.getwch

    def read(self) -> KeyPress:
        try:
            character = self._source()
        except KeyboardInterrupt:
            return KeyPress(Key.INTERRUPT)

        if character in WINDOWS_EXTENDED_PREFIXES:
            return KeyPress(KeyDecoder.extended(self._source()))

        control = KeyDecoder.control(character)
        if control is None:
            return KeyPress.of(character)
        if control is Key.ESCAPE:
            return KeyPress(Key.ESCAPE)
        return KeyPress(control)


class PosixKeyReader:
    def __init__(self, stream=None) -> None:
        self._stream = stream or sys.stdin

    def read(self) -> KeyPress:
        import termios
        import tty

        descriptor = self._stream.fileno()
        saved = termios.tcgetattr(descriptor)
        try:
            tty.setraw(descriptor)
            return self._decode()
        finally:
            termios.tcsetattr(descriptor, termios.TCSADRAIN, saved)

    def _decode(self) -> KeyPress:
        character = self._stream.read(1)
        if not character:
            return KeyPress(Key.END_OF_INPUT)

        control = KeyDecoder.control(character)
        if control is None:
            return KeyPress.of(character)
        if control is not Key.ESCAPE:
            return KeyPress(control)
        return self._escape()

    def _escape(self) -> KeyPress:
        body = ""
        while len(body) < MAXIMUM_SEQUENCE_LENGTH:
            body += self._stream.read(1)
            if KeyDecoder.is_complete_sequence(body):
                break
        if not body:
            return KeyPress(Key.ESCAPE)
        return KeyPress(KeyDecoder.sequence(body))


def create_key_reader() -> KeyReader:
    if sys.platform == "win32":
        return WindowsKeyReader()
    return PosixKeyReader()
