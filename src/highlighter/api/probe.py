from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config.schema import ApplicationConfig
from ..infrastructure.errors import HighlighterError
from ..media.encoders import EncoderSelector
from ..provisioning.archive import ArchiveExtractor
from ..provisioning.hlae_installation import HlaeInstallation
from ..recording.game_process import GameProcessWatcher
from .workspace import DemoWorkspace

HLAE_EXECUTABLE = "HLAE.exe"
FFMPEG_EXECUTABLE = "ffmpeg.exe"
HLAE_FOLDER = "hlae"
FFMPEG_FOLDER = "ffmpeg"


@dataclass(frozen=True, slots=True)
class ToolStatus:
    name: str
    ready: bool
    path: str = ""
    note: str = ""

    def to_mapping(self) -> dict[str, Any]:
        return {"name": self.name, "ready": self.ready, "path": self.path, "note": self.note}


class SystemProbe:
    def __init__(self, workspace: DemoWorkspace) -> None:
        self._workspace = workspace
        self._extractor = ArchiveExtractor()

    def report(self) -> dict[str, Any]:
        config = self._workspace.config
        game = self._game_status(config)
        hlae = self._hlae_status(config)
        ffmpeg = self._ffmpeg_status(config)
        tools = (game, hlae, ffmpeg)
        return {
            "ready": all(tool.ready for tool in tools),
            "tools": [tool.to_mapping() for tool in tools],
            "gameRunning": self._game_running(),
            "encoder": self._encoder(config, Path(ffmpeg.path) if ffmpeg.ready else None),
            "autoDownload": config.toolchain.auto_download,
            "demoDirectories": [
                str(directory) for directory in self._workspace.locator().search_directories
            ],
            "outputDirectory": str(
                self._workspace.paths.resolve(config.paths.output_directory)
            ),
        }

    def _game_status(self, config: ApplicationConfig) -> ToolStatus:
        installation = self._workspace.installation()
        if installation is None:
            return ToolStatus(
                name="cs2",
                ready=False,
                note="Counter-Strike 2 was not found, set paths.cs2Directory",
            )
        return ToolStatus(name="cs2", ready=True, path=str(installation.executable))

    def _hlae_status(self, config: ApplicationConfig) -> ToolStatus:
        found = self._locate(
            config.paths.hlae_executable, HLAE_FOLDER, HLAE_EXECUTABLE, config
        )
        if found is None:
            return ToolStatus(name="hlae", ready=False, note="HLAE is not installed yet")

        missing = HlaeInstallation(found, config.game.hook_dll_relative_path).missing_files()
        if missing:
            names = ", ".join(path.name for path in missing)
            return ToolStatus(
                name="hlae", ready=False, path=str(found), note=f"install incomplete: {names}"
            )
        return ToolStatus(name="hlae", ready=True, path=str(found))

    def _ffmpeg_status(self, config: ApplicationConfig) -> ToolStatus:
        found = self._locate(
            config.paths.ffmpeg_executable, FFMPEG_FOLDER, FFMPEG_EXECUTABLE, config
        )
        if found is None:
            return ToolStatus(name="ffmpeg", ready=False, note="ffmpeg is not installed yet")
        return ToolStatus(name="ffmpeg", ready=True, path=str(found))

    def _locate(
        self, configured: str, folder: str, executable_name: str, config: ApplicationConfig
    ) -> Path | None:
        if configured:
            candidate = Path(configured)
            return candidate if candidate.is_file() else None

        tools_directory = self._workspace.paths.resolve(config.paths.tools_directory)
        installed = self._extractor.find_executable(tools_directory / folder, executable_name)
        if installed is not None:
            return installed

        on_path = shutil.which(executable_name)
        return Path(on_path) if on_path else None

    def _game_running(self) -> bool:
        installation = self._workspace.installation()
        if installation is None:
            return False
        try:
            return GameProcessWatcher(installation.executable.name).is_running()
        except OSError:
            return False

    def _encoder(self, config: ApplicationConfig, ffmpeg: Path | None) -> dict[str, Any] | None:
        if ffmpeg is None:
            return None
        try:
            profile = EncoderSelector(ffmpeg, config.encoding).select()
        except HighlighterError:
            return None
        return {
            "codec": profile.codec,
            "container": profile.container,
            "hardware": profile.is_hardware,
        }
