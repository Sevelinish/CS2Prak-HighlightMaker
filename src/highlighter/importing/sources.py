from __future__ import annotations

import os
from pathlib import Path

from ..game.installation import Cs2Installation
from ..infrastructure.logging import get_logger
from .archives import ARCHIVE_SUFFIXES, DEMO_SUFFIX, DemoFile

DOWNLOADS_GUID = "{374DE290-123F-4565-9164-39C4925E467B}"
SHELL_FOLDERS_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
DOWNLOADS_FALLBACK = "~/Downloads"
WANTED_SUFFIXES = (DEMO_SUFFIX, *ARCHIVE_SUFFIXES)


class DownloadsFolder:
    @classmethod
    def locate(cls) -> Path | None:
        from_registry = cls._from_registry()
        if from_registry is not None and from_registry.is_dir():
            return from_registry

        fallback = Path(os.path.expanduser(DOWNLOADS_FALLBACK))
        return fallback if fallback.is_dir() else None

    @staticmethod
    def _from_registry() -> Path | None:
        try:
            import winreg
        except ImportError:
            return None

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SHELL_FOLDERS_KEY) as key:
                value, _ = winreg.QueryValueEx(key, DOWNLOADS_GUID)
        except OSError:
            return None
        return Path(os.path.expandvars(str(value)))


class DemoSourceLocator:
    def __init__(self, installation: Cs2Installation | None) -> None:
        self._installation = installation
        self._logger = get_logger("importing.sources")

    def directories(self) -> list[Path]:
        found: list[Path] = []
        downloads = DownloadsFolder.locate()
        if downloads is not None:
            found.append(downloads)
        if self._installation is not None:
            found.extend(self._installation.demo_directories())
        return [directory for directory in found if directory.is_dir()]

    def discover(self) -> list[DemoFile]:
        seen: dict[str, DemoFile] = {}
        for directory in self.directories():
            for candidate in sorted(directory.iterdir()):
                if not self._is_demo(candidate):
                    continue
                seen.setdefault(str(candidate.resolve()).lower(), DemoFile(candidate))

        found = sorted(seen.values(), key=lambda item: item.modified_at, reverse=True)
        self._logger.debug("Found %d demo file(s) outside the demo folder", len(found))
        return found

    @staticmethod
    def _is_demo(candidate: Path) -> bool:
        if not candidate.is_file():
            return False
        name = candidate.name.lower()
        if name.endswith(DEMO_SUFFIX):
            return True
        return any(
            name.endswith(f"{DEMO_SUFFIX}{suffix}") for suffix in ARCHIVE_SUFFIXES
        )
