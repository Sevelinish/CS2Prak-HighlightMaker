from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from ..config.schema import PathsConfig
from ..infrastructure.paths import ApplicationPaths
from ..provisioning.archive import ArchiveExtractor
from ..provisioning.hlae_installation import HlaeInstallation
from ..version import Version
from .probe import FileVersionReader, ProcessVersionReader

HLAE_KEY = "hlae"
FFMPEG_KEY = "ffmpeg"
CONFIGURED = "config.json"
INSTALLED = "tools folder"
ON_PATH = "on PATH"
NOWHERE = ""


@dataclass(frozen=True, slots=True)
class ToolStatus:
    key: str
    label: str
    executable: Path | None = None
    version_text: str = ""
    source: str = NOWHERE
    missing_files: tuple[Path, ...] = ()
    managed_root: Path | None = None

    @property
    def is_installed(self) -> bool:
        return self.executable is not None

    @property
    def is_complete(self) -> bool:
        return self.is_installed and not self.missing_files

    @property
    def version(self) -> Version | None:
        return Version.parse(self.version_text) if self.version_text else None

    @property
    def directory(self) -> Path | None:
        return self.executable.parent if self.executable is not None else None

    @property
    def missing_names(self) -> str:
        return ", ".join(path.name for path in self.missing_files)

    @property
    def is_managed(self) -> bool:
        return self.managed_root is not None

    @property
    def shown_version(self) -> str:
        parsed = self.version
        return str(parsed) if parsed is not None else self.version_text


class ToolInventory:
    def __init__(
        self,
        paths: PathsConfig,
        tools_directory: Path,
        hook_dll_relative_path: str = "",
        application_paths: ApplicationPaths | None = None,
    ) -> None:
        self._paths = paths
        self._tools_directory = tools_directory
        self._hook_dll_relative_path = hook_dll_relative_path
        self._application_paths = application_paths or ApplicationPaths.discover()
        self._extractor = ArchiveExtractor()
        self._file_version = FileVersionReader()
        self._process_version = ProcessVersionReader()

    def take(self) -> tuple[ToolStatus, ...]:
        return (self.hlae(), self.ffmpeg())

    def hlae(self) -> ToolStatus:
        found, source, root = self._locate(
            self._paths.hlae_executable, HLAE_KEY, "HLAE.exe"
        )
        if found is None:
            return ToolStatus(key=HLAE_KEY, label="HLAE")
        return ToolStatus(
            key=HLAE_KEY,
            label="HLAE",
            executable=found,
            version_text=self._file_version.read(found),
            source=source,
            missing_files=tuple(
                HlaeInstallation(found, self._hook_dll_relative_path).missing_files()
            ),
            managed_root=root,
        )

    def ffmpeg(self) -> ToolStatus:
        found, source, root = self._locate(
            self._paths.ffmpeg_executable, FFMPEG_KEY, "ffmpeg.exe"
        )
        if found is None:
            return ToolStatus(key=FFMPEG_KEY, label="ffmpeg")
        return ToolStatus(
            key=FFMPEG_KEY,
            label="ffmpeg",
            executable=found,
            version_text=self._process_version.read(found),
            source=source,
            managed_root=root,
        )

    def _locate(
        self, configured: str, folder: str, executable_name: str
    ) -> tuple[Path | None, str, Path | None]:
        if configured:
            candidate = self._application_paths.resolve(configured)
            return (candidate if candidate.is_file() else None), CONFIGURED, None

        root = self._tools_directory / folder
        installed = self._extractor.find_executable(root, executable_name)
        if installed is not None:
            return installed, INSTALLED, root

        on_path = shutil.which(executable_name)
        if on_path:
            return Path(on_path), ON_PATH, None
        return None, NOWHERE, None
