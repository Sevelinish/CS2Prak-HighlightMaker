from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass

from ..config.schema import ToolchainConfig
from ..infrastructure.errors import HighlighterError
from ..infrastructure.logging import get_logger
from ..provisioning.release_resolver import GITHUB_HEADERS, GithubReleaseResolver
from ..version import Version
from .inventory import FFMPEG_KEY, HLAE_KEY

MAXIMUM_BODY_BYTES = 256
NO_SOURCE = "no source is configured for this tool"


@dataclass(frozen=True, slots=True)
class LatestVersion:
    text: str = ""
    detail: str = ""
    error: str = ""

    @property
    def is_known(self) -> bool:
        return bool(self.text) and not self.error

    @property
    def version(self) -> Version | None:
        return Version.parse(self.text) if self.text else None

    @property
    def shown(self) -> str:
        parsed = self.version
        return str(parsed) if parsed is not None else self.text


class LatestVersionResolver:
    def __init__(self, settings: ToolchainConfig) -> None:
        self._settings = settings
        self._logger = get_logger("tooling")

    def for_tool(self, key: str) -> LatestVersion:
        if key == HLAE_KEY:
            return self.hlae()
        if key == FFMPEG_KEY:
            return self.ffmpeg()
        return LatestVersion(error=NO_SOURCE)

    def hlae(self) -> LatestVersion:
        if not self._settings.hlae_release_api_url or not self._settings.hlae_asset_pattern:
            return LatestVersion(error=NO_SOURCE)
        try:
            release = GithubReleaseResolver(
                self._settings.version_check_timeout_seconds
            ).resolve_release(
                self._settings.hlae_release_api_url, self._settings.hlae_asset_pattern
            )
        except HighlighterError as error:
            self._logger.debug("HLAE release check failed: %s", error)
            return LatestVersion(error=str(error))
        return LatestVersion(text=release.tag, detail=release.published_at[:10])

    def ffmpeg(self) -> LatestVersion:
        url = self._settings.ffmpeg_version_url
        if not url:
            return LatestVersion(error=NO_SOURCE)
        try:
            return LatestVersion(text=self._fetch(url))
        except (urllib.error.URLError, OSError, ValueError) as error:
            self._logger.debug("ffmpeg version check failed: %s", error)
            return LatestVersion(error=f"could not read {url}: {error}")

    def _fetch(self, url: str) -> str:
        request = urllib.request.Request(url, headers=GITHUB_HEADERS)
        with urllib.request.urlopen(
            request, timeout=self._settings.version_check_timeout_seconds
        ) as response:
            body = response.read(MAXIMUM_BODY_BYTES)
        return body.decode("utf-8", errors="replace").strip().splitlines()[0].strip()
