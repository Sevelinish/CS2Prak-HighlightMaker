from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from ..infrastructure.logging import get_logger
from .profile import DemoProfile

INDEX_VERSION = 1
INDEX_FILE_NAME = "demo_index.json"


class DemoIndex:
    def __init__(self, work_directory: Path) -> None:
        self._file = work_directory / INDEX_FILE_NAME
        self._profiles: dict[str, DemoProfile] = {}
        self._logger = get_logger("library.index")
        self._load()

    @property
    def file(self) -> Path:
        return self._file

    @property
    def count(self) -> int:
        return len(self._profiles)

    def knows(self, demo: Path) -> bool:
        key = DemoProfile.key_for(demo)
        return bool(key) and key in self._profiles

    def profile_for(self, demo: Path) -> DemoProfile | None:
        return self._profiles.get(DemoProfile.key_for(demo))

    def named(self, demo_name: str) -> DemoProfile | None:
        for profile in self.profiles():
            if profile.matches(demo_name):
                return profile
        return None

    def profiles(self) -> tuple[DemoProfile, ...]:
        return tuple(
            sorted(
                self._profiles.values(),
                key=lambda profile: profile.modified_at,
                reverse=True,
            )
        )

    def remember(self, profile: DemoProfile) -> None:
        if not profile.key:
            return
        self._profiles[profile.key] = profile
        self._save()

    def keep_only(self, demos: Iterable[Path]) -> int:
        alive = {key for key in (DemoProfile.key_for(demo) for demo in demos) if key}
        if not alive:
            return 0
        stale = [key for key in self._profiles if key not in alive]
        for key in stale:
            del self._profiles[key]
        if stale:
            self._save()
        return len(stale)

    def _load(self) -> None:
        if not self._file.is_file():
            return
        try:
            raw = json.loads(self._file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._logger.debug("The demo index could not be read, starting a new one")
            return
        if not isinstance(raw, dict) or int(raw.get("version") or 0) != INDEX_VERSION:
            return

        for entry in raw.get("demos") or []:
            if not isinstance(entry, dict):
                continue
            profile = DemoProfile.from_mapping(entry)
            if profile is not None:
                self._profiles[profile.key] = profile

    def _save(self) -> None:
        payload = {
            "version": INDEX_VERSION,
            "demos": [profile.to_mapping() for profile in self.profiles()],
        }
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            self._file.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        except OSError as error:
            self._logger.debug("The demo index could not be written: %s", error)
