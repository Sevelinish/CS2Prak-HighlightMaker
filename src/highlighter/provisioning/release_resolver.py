from __future__ import annotations

import fnmatch
import json
import urllib.error
import urllib.request

from ..infrastructure.errors import DownloadError
from ..infrastructure.logging import get_logger

GITHUB_HEADERS = {
    "User-Agent": "HighlighterCS2",
    "Accept": "application/vnd.github+json",
}
SIGNATURE_SUFFIX = ".asc"


class GithubReleaseResolver:
    def __init__(self, timeout_seconds: int) -> None:
        self._timeout_seconds = timeout_seconds
        self._logger = get_logger("toolchain.release")

    def resolve_asset_url(self, api_url: str, asset_pattern: str) -> str:
        release = self._fetch(api_url)
        assets = release.get("assets") or []

        for asset in assets:
            name = str(asset.get("name", ""))
            if name.endswith(SIGNATURE_SUFFIX):
                continue
            if fnmatch.fnmatch(name.lower(), asset_pattern.lower()):
                self._logger.debug("Resolved %s to asset %s", release.get("tag_name"), name)
                return str(asset["browser_download_url"])

        raise DownloadError(
            f"No asset matching '{asset_pattern}' in release {release.get('tag_name', api_url)}"
        )

    def _fetch(self, api_url: str) -> dict:
        request = urllib.request.Request(api_url, headers=GITHUB_HEADERS)
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                return json.load(response)
        except (urllib.error.URLError, json.JSONDecodeError) as error:
            raise DownloadError(f"Could not read release metadata from {api_url}: {error}") from error
