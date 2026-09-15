from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config.schema import UpdateConfig
from ..provisioning.release_resolver import GithubReleaseResolver, ReleaseInfo
from ..version import Version


@dataclass(frozen=True, slots=True)
class UpdateCheck:
    current: Version
    latest: Version | None = None
    release: ReleaseInfo | None = None

    @property
    def available(self) -> bool:
        return self.latest is not None and self.latest.is_newer_than(self.current)

    @property
    def is_unknown(self) -> bool:
        return self.latest is None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "current": str(self.current),
            "latest": str(self.latest) if self.latest is not None else None,
            "available": self.available,
            "release": self.release.to_mapping() if self.release is not None else None,
        }


class UpdateChecker:
    def __init__(self, settings: UpdateConfig, current: Version | None = None) -> None:
        self._settings = settings
        self._current = current or Version.current()
        self._resolver = GithubReleaseResolver(settings.timeout_seconds)

    @property
    def current(self) -> Version:
        return self._current

    def check(self) -> UpdateCheck:
        release = self._resolver.resolve_release(
            self._settings.release_api_url, self._settings.asset_pattern
        )
        return UpdateCheck(
            current=self._current,
            latest=Version.parse(release.tag),
            release=release,
        )
