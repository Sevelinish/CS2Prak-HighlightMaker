from __future__ import annotations

import ctypes
import re
import subprocess
import sys
from pathlib import Path

from ..infrastructure.logging import get_logger

ROOT_BLOCK = chr(92)
VERSION_SIGNATURE = 0xFEEF04BD
VERSION_LINE_PATTERN = re.compile(r"version\s+(\S+)", re.IGNORECASE)
PROCESS_TIMEOUT_SECONDS = 10
NO_WINDOW = 0x08000000


class FixedFileInfo(ctypes.Structure):
    _fields_ = [
        ("dwSignature", ctypes.c_uint32),
        ("dwStrucVersion", ctypes.c_uint32),
        ("dwFileVersionMS", ctypes.c_uint32),
        ("dwFileVersionLS", ctypes.c_uint32),
        ("dwProductVersionMS", ctypes.c_uint32),
        ("dwProductVersionLS", ctypes.c_uint32),
        ("dwFileFlagsMask", ctypes.c_uint32),
        ("dwFileFlags", ctypes.c_uint32),
        ("dwFileOS", ctypes.c_uint32),
        ("dwFileType", ctypes.c_uint32),
        ("dwFileSubtype", ctypes.c_uint32),
        ("dwFileDateMS", ctypes.c_uint32),
        ("dwFileDateLS", ctypes.c_uint32),
    ]


class FileVersionReader:
    def __init__(self) -> None:
        self._logger = get_logger("tooling")

    def read(self, executable: Path) -> str:
        if sys.platform != "win32":
            return ""
        try:
            return self._from_resource(str(executable))
        except (AttributeError, OSError, ValueError):
            self._logger.debug("No version resource in %s", executable, exc_info=True)
            return ""

    def _from_resource(self, path: str) -> str:
        library = ctypes.windll.version
        size = library.GetFileVersionInfoSizeW(path, None)
        if not size:
            return ""

        buffer = ctypes.create_string_buffer(size)
        if not library.GetFileVersionInfoW(path, 0, size, buffer):
            return ""

        pointer = ctypes.c_void_p()
        length = ctypes.c_uint()
        if not library.VerQueryValueW(
            buffer, ROOT_BLOCK, ctypes.byref(pointer), ctypes.byref(length)
        ):
            return ""

        info = ctypes.cast(pointer, ctypes.POINTER(FixedFileInfo)).contents
        if info.dwSignature != VERSION_SIGNATURE:
            return ""
        return self._render(info.dwFileVersionMS, info.dwFileVersionLS)

    @staticmethod
    def _render(most: int, least: int) -> str:
        parts = (most >> 16, most & 0xFFFF, least >> 16, least & 0xFFFF)
        while len(parts) > 3 and parts[-1] == 0:
            parts = parts[:-1]
        return ".".join(str(part) for part in parts)


class ProcessVersionReader:
    def __init__(self, argument: str = "-version") -> None:
        self._argument = argument
        self._logger = get_logger("tooling")

    def read(self, executable: Path) -> str:
        try:
            finished = subprocess.run(
                [str(executable), self._argument],
                capture_output=True,
                text=True,
                timeout=PROCESS_TIMEOUT_SECONDS,
                creationflags=NO_WINDOW if sys.platform == "win32" else 0,
            )
        except (OSError, subprocess.SubprocessError):
            self._logger.debug("Could not ask %s for its version", executable, exc_info=True)
            return ""

        return self._first_version(finished.stdout or finished.stderr)

    @staticmethod
    def _first_version(output: str) -> str:
        line = (output or "").strip().splitlines()[:1]
        if not line:
            return ""
        match = VERSION_LINE_PATTERN.search(line[0])
        return match.group(1) if match is not None else ""
