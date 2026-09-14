from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from ..config.schema import ApplicationConfig, DetectionConfig
from ..demo.grenade_reader import GrenadeReader
from ..demo.locator import DemoLocator
from ..demo.reader import DemoReader
from ..detection.engine import HighlightEngine
from ..domain.grenade import Grenade, GrenadeKind
from ..domain.highlight import Highlight
from ..domain.match import Match
from ..game.installation import Cs2Installation
from ..infrastructure.errors import GameNotFoundError
from ..infrastructure.paths import ApplicationPaths
from .errors import DemoNotFoundApiError


@dataclass(frozen=True, slots=True)
class CacheKey:
    path: str
    modified_at: float

    @classmethod
    def of(cls, path: Path) -> "CacheKey":
        try:
            return cls(path=str(path).lower(), modified_at=path.stat().st_mtime)
        except OSError:
            return cls(path=str(path).lower(), modified_at=0.0)


class DemoWorkspace:
    def __init__(self, paths: ApplicationPaths, config: ApplicationConfig) -> None:
        self._paths = paths
        self._config = config
        self._lock = threading.RLock()
        self._matches: dict[CacheKey, Match] = {}
        self._highlights: dict[tuple[CacheKey, str], list[Highlight]] = {}
        self._grenades: dict[tuple[CacheKey, str], list[Grenade]] = {}

    @property
    def config(self) -> ApplicationConfig:
        return self._config

    @property
    def paths(self) -> ApplicationPaths:
        return self._paths

    def adopt(self, config: ApplicationConfig) -> None:
        with self._lock:
            self._config = config
            self._highlights.clear()
            self._grenades.clear()

    def installation(self) -> Cs2Installation | None:
        try:
            return Cs2Installation.discover(self._config.paths.cs2_directory)
        except GameNotFoundError:
            return None

    def locator(self) -> DemoLocator:
        directories = [self._paths.resolve(self._config.paths.demo_directory)]
        installation = self.installation()
        if installation is not None:
            directories.extend(installation.demo_directories())
        return DemoLocator(directories)

    def demos(self) -> list[Path]:
        return self.locator().discover()

    def resolve(self, given: str) -> Path:
        cleaned = (given or "").strip()
        if not cleaned:
            raise DemoNotFoundApiError(cleaned, self.locator())

        direct = self._paths.resolve(cleaned)
        if DemoLocator.is_demo(direct):
            return direct

        locator = self.locator()
        found = locator.find_by_name(Path(cleaned).name)
        if found is None:
            raise DemoNotFoundApiError(cleaned, locator)
        return found

    def match(self, demo_path: Path, refresh: bool = False) -> Match:
        key = CacheKey.of(demo_path)
        with self._lock:
            cached = None if refresh else self._matches.get(key)
        if cached is not None:
            return cached

        parsed = DemoReader(demo_path, self._config.game.tick_rate).read()
        with self._lock:
            self._matches[key] = parsed
        return parsed

    def highlights(
        self,
        demo_path: Path,
        detection: DetectionConfig | None = None,
        refresh: bool = False,
    ) -> list[Highlight]:
        settings = detection or self._config.detection
        key = (CacheKey.of(demo_path), self._detection_signature(settings))
        with self._lock:
            cached = None if refresh else self._highlights.get(key)
        if cached is not None:
            return list(cached)

        detected = HighlightEngine(settings).detect(self.match(demo_path))
        with self._lock:
            self._highlights[key] = detected
        return list(detected)

    def grenades(
        self,
        demo_path: Path,
        kinds: tuple[GrenadeKind, ...],
        refresh: bool = False,
    ) -> list[Grenade]:
        wanted = kinds or tuple(GrenadeKind)
        key = (CacheKey.of(demo_path), ",".join(kind.value for kind in wanted))
        with self._lock:
            cached = None if refresh else self._grenades.get(key)
        if cached is not None:
            return list(cached)

        read = GrenadeReader(
            demo_path, self.match(demo_path), self._config.nades.callout_sample_stride
        ).read(wanted)
        with self._lock:
            self._grenades[key] = read
        return list(read)

    @staticmethod
    def _detection_signature(settings: DetectionConfig) -> str:
        return (
            f"{settings.minimum_kills}:{settings.minimum_score}:"
            f"{settings.maximum_highlights}:{sorted(settings.tag_weights.items())}:"
            f"{sorted(settings.enabled_rules)}"
        )
