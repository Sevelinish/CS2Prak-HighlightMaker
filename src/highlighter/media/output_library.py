from __future__ import annotations

from pathlib import Path
from typing import Sequence

PARTS_FOLDER = "parts"
REEL_SUFFIX = "highlights"


class OutputLibrary:
    def __init__(
        self, root: Path, demo_name: str, container: str, single_file: bool = False
    ) -> None:
        self._root = root
        self._demo_name = demo_name
        self._container = container.lstrip(".")
        self._single_file = single_file

    @property
    def directory(self) -> Path:
        return self._root / self._demo_name

    @property
    def parts_directory(self) -> Path:
        if self._single_file:
            return self.directory / PARTS_FOLDER
        return self.directory

    def prepare(self) -> Path:
        self.parts_directory.mkdir(parents=True, exist_ok=True)
        return self.directory

    @property
    def superseded_directory(self) -> Path:
        if self._single_file:
            return self.directory
        return self.directory / PARTS_FOLDER

    def retire_superseded(self, clip_names: Sequence[str]) -> list[Path]:
        retired: list[Path] = []
        for name in clip_names:
            stale = self.superseded_directory / f"{name}.{self._container}"
            if stale.is_file():
                stale.unlink(missing_ok=True)
                retired.append(stale)

        if not self._single_file:
            pattern = f"{self._demo_name}_{REEL_SUFFIX}*.{self._container}"
            for reel in sorted(self.directory.glob(pattern)):
                reel.unlink(missing_ok=True)
                retired.append(reel)

        self._remove_empty(self.directory / PARTS_FOLDER)
        return retired

    @staticmethod
    def _remove_empty(directory: Path) -> None:
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()

    def destination_for(self, clip_name: str) -> Path:
        return self._unique(self.parts_directory / f"{clip_name}.{self._container}")

    def reel_destination(self) -> Path:
        return self._unique(
            self.directory / f"{self._demo_name}_{REEL_SUFFIX}.{self._container}"
        )

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
