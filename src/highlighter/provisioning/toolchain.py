from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from rich.console import Console

from ..config.schema import PathsConfig, ToolchainConfig
from ..infrastructure.errors import ToolchainError
from ..infrastructure.logging import get_logger
from .archive import ArchiveExtractor
from .downloader import FileDownloader
from .hlae_installation import HlaeInstallation
from .release_resolver import GithubReleaseResolver

HLAE_EXECUTABLE = "HLAE.exe"
FFMPEG_EXECUTABLE = "ffmpeg.exe"


@dataclass(frozen=True, slots=True)
class ToolSpecification:
    key: str
    label: str
    executable_name: str
    install_folder: str
    download_url: str = ""
    release_api_url: str = ""
    asset_pattern: str = ""
    validate: Callable[[Path], list[Path]] | None = None


@dataclass(frozen=True, slots=True)
class Toolchain:
    hlae: Path
    ffmpeg: Path


class ToolchainProvisioner:
    def __init__(
        self,
        console: Console,
        paths: PathsConfig,
        settings: ToolchainConfig,
        tools_directory: Path,
        hook_dll_relative_path: str = "",
    ) -> None:
        self._console = console
        self._paths = paths
        self._settings = settings
        self._tools_directory = tools_directory
        self._hook_dll_relative_path = hook_dll_relative_path
        self._downloader = FileDownloader(console, settings.download_timeout_seconds)
        self._release_resolver = GithubReleaseResolver(settings.download_timeout_seconds)
        self._extractor = ArchiveExtractor()
        self._logger = get_logger("toolchain")

    def provision(self) -> Toolchain:
        return Toolchain(
            hlae=self._resolve(
                ToolSpecification(
                    key="hlae",
                    label="HLAE",
                    executable_name=HLAE_EXECUTABLE,
                    install_folder="hlae",
                    download_url=self._settings.hlae_download_url,
                    release_api_url=self._settings.hlae_release_api_url,
                    asset_pattern=self._settings.hlae_asset_pattern,
                    validate=self._missing_hlae_files,
                ),
                self._paths.hlae_executable,
            ),
            ffmpeg=self._resolve(
                ToolSpecification(
                    key="ffmpeg",
                    label="ffmpeg",
                    executable_name=FFMPEG_EXECUTABLE,
                    install_folder="ffmpeg",
                    download_url=self._settings.ffmpeg_download_url,
                ),
                self._paths.ffmpeg_executable,
            ),
        )

    def _resolve(self, specification: ToolSpecification, configured: str) -> Path:
        explicit = self._from_configuration(configured, specification)
        if explicit is not None:
            return self._require_complete(specification, explicit)

        install_root = self._tools_directory / specification.install_folder
        installed = self._extractor.find_executable(install_root, specification.executable_name)
        if installed is not None and self._is_complete(specification, installed):
            return installed

        if installed is not None:
            self._report_damaged(specification, installed)
            shutil.rmtree(install_root, ignore_errors=True)

        on_path = shutil.which(specification.executable_name)
        if on_path and self._is_complete(specification, Path(on_path)):
            return Path(on_path)

        if not self._settings.auto_download:
            raise ToolchainError(
                f"{specification.label} is missing. Enable toolchain.autoDownload "
                f"or set its path in config.json."
            )

        return self._require_complete(
            specification, self._install(specification, install_root)
        )

    def _missing_files(self, specification: ToolSpecification, executable: Path) -> list[Path]:
        if specification.validate is None:
            return []
        return specification.validate(executable)

    def _is_complete(self, specification: ToolSpecification, executable: Path) -> bool:
        return not self._missing_files(specification, executable)

    def _require_complete(self, specification: ToolSpecification, executable: Path) -> Path:
        missing = self._missing_files(specification, executable)
        if missing:
            names = ", ".join(path.name for path in missing)
            raise ToolchainError(
                f"{specification.label} install at {executable.parent} is incomplete "
                f"(missing: {names})."
            )
        return executable

    def _report_damaged(self, specification: ToolSpecification, executable: Path) -> None:
        missing = self._missing_files(specification, executable)
        names = ", ".join(path.name for path in missing)
        self._logger.warning(
            "%s install is damaged, missing: %s", specification.label, names
        )
        self._console.print(
            f"[warning]{specification.label} install is damaged "
            f"(missing {names}), reinstalling it[/warning]"
        )

    def _missing_hlae_files(self, executable: Path) -> list[Path]:
        return HlaeInstallation(executable, self._hook_dll_relative_path).missing_files()

    def _from_configuration(
        self, configured: str, specification: ToolSpecification
    ) -> Path | None:
        if not configured:
            return None
        candidate = Path(configured)
        if candidate.is_file():
            return candidate
        raise ToolchainError(
            f"Configured {specification.label} path does not exist: {candidate}"
        )

    def _install(self, specification: ToolSpecification, install_root: Path) -> Path:
        self._console.print(
            f"[muted]{specification.label} not found, downloading it once...[/muted]"
        )
        archive = self._tools_directory / f"{specification.key}.zip"
        try:
            self._downloader.download(
                self._resolve_download_url(specification), archive, specification.label
            )
            self._extractor.extract(archive, install_root)
        finally:
            archive.unlink(missing_ok=True)

        executable = self._extractor.find_executable(
            install_root, specification.executable_name
        )
        if executable is None:
            raise ToolchainError(
                f"{specification.executable_name} was not found inside the "
                f"{specification.label} archive"
            )

        self._logger.info("Installed %s at %s", specification.label, executable)
        self._console.print(f"[success]{specification.label} ready[/success] [muted]{executable}[/muted]")
        return executable

    def _resolve_download_url(self, specification: ToolSpecification) -> str:
        if specification.download_url:
            return specification.download_url
        if specification.release_api_url and specification.asset_pattern:
            return self._release_resolver.resolve_asset_url(
                specification.release_api_url, specification.asset_pattern
            )
        raise ToolchainError(f"No download source configured for {specification.label}")
