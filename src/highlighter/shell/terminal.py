from __future__ import annotations

import shutil
import sys

ESCAPE = "\x1b"
CSI = f"{ESCAPE}["
RESET = f"{CSI}0m"
ERASE_LINE = f"{CSI}K"
CARRIAGE_RETURN = "\r"
NEWLINE = "\n"
CLEAR_SCREEN = f"{CSI}2J{CSI}H"

PROMPT_STYLE = f"{CSI}1;35m"
GHOST_STYLE = f"{CSI}38;5;244m"
HINT_STYLE = f"{CSI}38;5;240m"

VIRTUAL_TERMINAL_PROCESSING = 0x0004
STANDARD_OUTPUT = -11
FALLBACK_WIDTH = 100
MINIMUM_WIDTH = 40


class Terminal:
    def __init__(self, stream=None) -> None:
        self._stream = stream or sys.stdout

    @property
    def width(self) -> int:
        try:
            columns = shutil.get_terminal_size(fallback=(FALLBACK_WIDTH, 24)).columns
        except (OSError, ValueError):
            return FALLBACK_WIDTH
        return max(MINIMUM_WIDTH, columns)

    def write(self, text: str) -> None:
        self._stream.write(text)

    def flush(self) -> None:
        try:
            self._stream.flush()
        except (OSError, ValueError):
            pass

    def column(self, index: int) -> str:
        if index <= 0:
            return CARRIAGE_RETURN
        return f"{CARRIAGE_RETURN}{CSI}{index}C"


class TerminalCapabilities:
    @staticmethod
    def is_interactive() -> bool:
        return TerminalCapabilities._is_tty(sys.stdin) and TerminalCapabilities._is_tty(
            sys.stdout
        )

    @staticmethod
    def supports_line_editing() -> bool:
        if not TerminalCapabilities.is_interactive():
            return False
        if sys.platform == "win32":
            return TerminalCapabilities.enable_virtual_terminal()
        return True

    @staticmethod
    def enable_virtual_terminal() -> bool:
        if sys.platform != "win32":
            return True
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(STANDARD_OUTPUT)
            mode = ctypes.c_uint32()
            if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                return False
            return bool(
                kernel32.SetConsoleMode(
                    handle, mode.value | VIRTUAL_TERMINAL_PROCESSING
                )
            )
        except (AttributeError, OSError, ValueError):
            return False

    @staticmethod
    def _is_tty(stream) -> bool:
        try:
            return bool(stream is not None and stream.isatty())
        except (AttributeError, OSError, ValueError):
            return False
