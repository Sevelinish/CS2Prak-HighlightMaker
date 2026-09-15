from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from ..config.schema import UpdateConfig
from ..infrastructure.errors import HighlighterError
from ..infrastructure.logging import get_logger
from ..provisioning.archive import ArchiveExtractor
from ..provisioning.downloader import FileDownloader
from ..provisioning.release_resolver import ReleaseInfo
from ..version import Version

RELEASE_EXECUTABLE = "HighlighterCS2.exe"
BUNDLE_DIRECTORY = "_internal"
STAGED_DIRECTORY = "staged"


class UpdateError(HighlighterError):
    pass


@dataclass(frozen=True, slots=True)
class UpdatePayload:
    root: Path
    archive: Path
    version: Version

    @property
    def executable(self) -> Path:
        return self.root / RELEASE_EXECUTABLE


class PayloadStager:
    def __init__(
        self, console: Console, settings: UpdateConfig, staging_directory: Path
    ) -> None:
        self._console = console
        self._settings = settings
        self._staging = staging_directory
        self._extractor = ArchiveExtractor()
        self._logger = get_logger("update")

    @property
    def staging_directory(self) -> Path:
        return self._staging

    def stage(self, release: ReleaseInfo) -> UpdatePayload:
        self.clean()
        self._staging.mkdir(parents=True, exist_ok=True)

        archive = self._download(release)
        extracted = self._staging / STAGED_DIRECTORY
        try:
            self._extractor.extract(archive, extracted)
        except HighlighterError as error:
            raise UpdateError(f"The downloaded release could not be opened: {error}") from error

        root = self._locate_root(extracted, release)
        self._verify(root, release)
        self._logger.info("Staged release %s at %s", release.tag, root)
        return UpdatePayload(
            root=root, archive=archive, version=Version.parse(release.tag) or Version()
        )

    def clean(self) -> None:
        shutil.rmtree(self._staging / STAGED_DIRECTORY, ignore_errors=True)

    def _download(self, release: ReleaseInfo) -> Path:
        destination = self._staging / (release.asset_name or "release.zip")
        downloader = FileDownloader(self._console, self._settings.timeout_seconds)
        return downloader.download(release.asset_url, destination, release.asset_name)

    def _locate_root(self, extracted: Path, release: ReleaseInfo) -> Path:
        executable = self._extractor.find_executable(extracted, RELEASE_EXECUTABLE)
        if executable is None:
            raise UpdateError(
                f"{release.asset_name} does not contain {RELEASE_EXECUTABLE}, "
                f"so it is not a HighlighterCS2 release"
            )
        return executable.parent

    @staticmethod
    def _verify(root: Path, release: ReleaseInfo) -> None:
        bundle = root / BUNDLE_DIRECTORY
        if not bundle.is_dir():
            raise UpdateError(
                f"{release.asset_name} is missing its {BUNDLE_DIRECTORY} folder, "
                f"the release looks incomplete"
            )
