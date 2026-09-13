from __future__ import annotations

from pathlib import Path


class OutputLibrary:
    def __init__(self, root: Path, demo_name: str, container: str) -> None:
        self._root = root
        self._demo_name = demo_name
        self._container = container.lstrip(".")

    @property
    def directory(self) -> Path:
        return self._root / self._demo_name

    def prepare(self) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        return self.directory

    def destination_for(self, clip_name: str) -> Path:
        return self._unique(self.directory / f"{clip_name}.{self._container}")

    @staticmethod
    def _unique(candidate: Path) -> Path:
        if not candidate.exists():
            return candidate
        stem, suffix = candidate.stem, candidate.suffix
        counter = 2
        while True:
            alternative = candidate.with_name(f"{stem}_{counter}{suffix}")
            if not alternative.exists():
                return alternative
            counter += 1
