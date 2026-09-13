from __future__ import annotations

from pathlib import Path

from ..infrastructure.errors import GameNotFoundError
from .steam import SteamInstallation

CS2_FOLDER_NAME = "Counter-Strike Global Offensive"
CS2_APP_ID = "730"
EXECUTABLE_RELATIVE_PATH = Path("game/bin/win64/cs2.exe")
CONFIG_RELATIVE_PATH = Path("game/csgo/cfg")
DEMO_RELATIVE_PATHS = (Path("game/csgo"), Path("game/csgo/replays"))
VIDEO_SETTINGS_FILE = "cs2_video.txt"


class Cs2Installation:
    def __init__(self, root: Path, steam: SteamInstallation | None = None) -> None:
        self._root = root
        self._steam = steam

    @classmethod
    def discover(cls, configured_directory: str = "") -> "Cs2Installation":
        steam = SteamInstallation.discover()

        if configured_directory:
            candidate = Path(configured_directory)
            if cls._is_valid_root(candidate):
                return cls(candidate, steam)
            raise GameNotFoundError(
                f"paths.cs2Directory does not look like a CS2 install: {candidate}"
            )

        if steam is not None:
            found = steam.find_app_directory(CS2_FOLDER_NAME)
            if found is not None and cls._is_valid_root(found):
                return cls(found, steam)

        raise GameNotFoundError(
            "Counter-Strike 2 was not found. Set paths.cs2Directory in config.json."
        )

    @property
    def root(self) -> Path:
        return self._root

    @property
    def steam_root(self) -> Path | None:
        return self._steam.root if self._steam is not None else None

    @property
    def executable(self) -> Path:
        return self._root / EXECUTABLE_RELATIVE_PATH

    @property
    def config_directory(self) -> Path:
        return self._root / CONFIG_RELATIVE_PATH

    def demo_directories(self) -> list[Path]:
        return [self._root / relative for relative in DEMO_RELATIVE_PATHS]

    def video_settings_files(self) -> list[Path]:
        if self._steam is None or not self._steam.userdata.is_dir():
            return []
        return [
            account / CS2_APP_ID / "local" / "cfg" / VIDEO_SETTINGS_FILE
            for account in self._steam.userdata.iterdir()
            if account.is_dir()
        ]

    @staticmethod
    def _is_valid_root(candidate: Path) -> bool:
        return (candidate / EXECUTABLE_RELATIVE_PATH).is_file()
