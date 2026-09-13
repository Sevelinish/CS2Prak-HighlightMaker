from __future__ import annotations

import re
import winreg
from pathlib import Path

LIBRARY_PATH_PATTERN = re.compile(r'"path"\s+"([^"]+)"', re.IGNORECASE)
STEAM_REGISTRY_KEYS = (
    (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
)
COMMON_STEAM_DIRECTORIES = (
    Path(r"C:\Program Files (x86)\Steam"),
    Path(r"C:\Program Files\Steam"),
)


class SteamInstallation:
    def __init__(self, root: Path) -> None:
        self._root = root

    @classmethod
    def discover(cls) -> "SteamInstallation | None":
        for candidate in cls._candidate_roots():
            if (candidate / "steamapps").is_dir():
                return cls(candidate)
        return None

    @property
    def root(self) -> Path:
        return self._root

    @property
    def userdata(self) -> Path:
        return self._root / "userdata"

    def library_roots(self) -> list[Path]:
        roots = [self._root]
        manifest = self._root / "steamapps" / "libraryfolders.vdf"
        if not manifest.is_file():
            return roots

        try:
            content = manifest.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return roots

        for raw_path in LIBRARY_PATH_PATTERN.findall(content):
            candidate = Path(raw_path.replace("\\\\", "\\"))
            if candidate.is_dir() and candidate not in roots:
                roots.append(candidate)
        return roots

    def find_app_directory(self, folder_name: str) -> Path | None:
        for root in self.library_roots():
            candidate = root / "steamapps" / "common" / folder_name
            if candidate.is_dir():
                return candidate
        return None

    @staticmethod
    def _candidate_roots() -> list[Path]:
        roots: list[Path] = []
        for hive, subkey, value_name in STEAM_REGISTRY_KEYS:
            resolved = SteamInstallation._read_registry(hive, subkey, value_name)
            if resolved is not None and resolved not in roots:
                roots.append(resolved)
        for fallback in COMMON_STEAM_DIRECTORIES:
            if fallback not in roots:
                roots.append(fallback)
        return roots

    @staticmethod
    def _read_registry(hive: int, subkey: str, value_name: str) -> Path | None:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                value, _ = winreg.QueryValueEx(key, value_name)
        except OSError:
            return None
        candidate = Path(str(value))
        return candidate if candidate.is_dir() else None
