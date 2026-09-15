from __future__ import annotations

import fnmatch
import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from ..infrastructure.errors import DownloadError
from ..infrastructure.logging import get_logger

GITHUB_HEADERS = {
    "User-Agent": "HighlighterCS2",
    "Accept": "application/vnd.github+json",
}
SIGNATURE_SUFFIX = ".asc"


@dataclass(frozen=True, slots=True)
class ReleaseInfo:
    tag: str
    name: str
    asset_name: str
    asset_url: str
    size_bytes: int = 0
    published_at: str = ""
    notes: str = ""
    page_url: str = ""

    def to_mapping(self) -> dict:
        return {
            "tag": self.tag,
            "name": self.name,
            "assetName": self.asset_name,
            "sizeBytes": self.size_bytes,
            "publishedAt": self.published_at,
            "pageUrl": self.page_url,
        }


class GithubReleaseResolver:
    def __init__(self, timeout_seconds: int) -> None:
        self._timeout_seconds = timeout_seconds
        self._logger = get_logger("toolchain.release")

    def resolve_asset_url(self, api_url: str, asset_pattern: str) -> str:
        return self.resolve_release(api_url, asset_pattern).asset_url

    def resolve_release(self, api_url: str, asset_pattern: str) -> ReleaseInfo:
        release = self._fetch(api_url)
        asset = self._matching_asset(release, asset_pattern, api_url)
        return ReleaseInfo(
            tag=str(release.get("tag_name") or ""),
            name=str(release.get("name") or release.get("tag_name") or ""),
            asset_name=str(asset.get("name") or ""),
            asset_url=str(asset["browser_download_url"]),
            size_bytes=int(asset.get("size") or 0),
            published_at=str(release.get("published_at") or ""),
            notes=str(release.get("body") or ""),
            page_url=str(release.get("html_url") or ""),
        )

    def _matching_asset(self, release: dict, asset_pattern: str, api_url: str) -> dict:
        for asset in release.get("assets") or []:
            name = str(asset.get("name", ""))
            if name.endswith(SIGNATURE_SUFFIX):
                continue
            if fnmatch.fnmatch(name.lower(), asset_pattern.lower()):
                self._logger.debug("Resolved %s to asset %s", release.get("tag_name"), name)
                return asset

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
