from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..config.repository import ConfigRepository
from ..config.schema import ApplicationConfig
from ..infrastructure.logging import get_logger
from ..shell.reader import KeyReader, create_key_reader
from .editor import EditorOutcome, TextEditor
from .screen import EditorScreen
from .validator import JsonValidator

WINDOWS_NEWLINE = "\r\n"
UNIX_NEWLINE = "\n"
TEMPORARY_SUFFIX = ".editing"


@dataclass(frozen=True, slots=True)
class ConfigEditOutcome:
    saved: bool = False
    dropped_keys: tuple[str, ...] = ()

    @property
    def has_strays(self) -> bool:
        return bool(self.dropped_keys)


class ConfigFile:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._newline = UNIX_NEWLINE

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> str:
        raw = self._path.read_bytes()
        self._newline = WINDOWS_NEWLINE if WINDOWS_NEWLINE.encode() in raw else UNIX_NEWLINE
        return raw.decode("utf-8-sig").replace(WINDOWS_NEWLINE, UNIX_NEWLINE)

    def write(self, text: str) -> None:
        body = text if text.endswith(UNIX_NEWLINE) else text + UNIX_NEWLINE
        staged = self._path.with_suffix(self._path.suffix + TEMPORARY_SUFFIX)
        staged.write_bytes(body.replace(UNIX_NEWLINE, self._newline).encode("utf-8"))
        os.replace(staged, self._path)


class StraySettingFinder:
    def find(self, raw: Mapping[str, Any]) -> tuple[str, ...]:
        known = ApplicationConfig.from_mapping(raw).to_mapping()
        return tuple(self._walk(raw, known, ""))

    def _walk(self, raw: Mapping[str, Any], known: Mapping[str, Any], prefix: str):
        for key, value in raw.items():
            path = f"{prefix}{key}"
            if key not in known:
                yield path
                continue
            if isinstance(value, dict) and isinstance(known[key], dict):
                yield from self._walk(value, known[key], f"{path}.")


class ConfigEditor:
    def __init__(
        self,
        config_file: Path,
        reader: KeyReader | None = None,
        screen: EditorScreen | None = None,
    ) -> None:
        self._file = ConfigFile(config_file)
        self._reader = reader
        self._screen = screen
        self._logger = get_logger("editor")

    @property
    def path(self) -> Path:
        return self._file.path

    def run(self) -> ConfigEditOutcome:
        ConfigRepository(self._file.path).load()
        outcome = self._edit(self._file.read())
        if not outcome.saved:
            return ConfigEditOutcome()
        return ConfigEditOutcome(saved=True, dropped_keys=self._strays(outcome.text))

    def _edit(self, text: str) -> EditorOutcome:
        editor = TextEditor(
            reader=self._reader or create_key_reader(),
            screen=self._screen or EditorScreen(),
            title=str(self._file.path),
            validator=JsonValidator(ApplicationConfig.from_mapping),
            writer=self._file.write,
        )
        return editor.edit(text)

    def _strays(self, text: str) -> tuple[str, ...]:
        try:
            raw = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return ()
        if not isinstance(raw, dict):
            return ()
        try:
            return StraySettingFinder().find(raw)
        except (KeyError, TypeError, ValueError):
            self._logger.debug("Could not look for stray settings", exc_info=True)
            return ()
