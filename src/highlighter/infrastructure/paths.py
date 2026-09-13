from __future__ import annotations

import sys
from pathlib import Path


class ApplicationPaths:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    @classmethod
    def discover(cls) -> "ApplicationPaths":
        if getattr(sys, "frozen", False):
            return cls(Path(sys.executable).parent)
        return cls(Path(__file__).resolve().parents[3])

    @property
    def root(self) -> Path:
        return self._root

    @property
    def config_file(self) -> Path:
        return self._root / "config.json"

    @property
    def logs(self) -> Path:
        return self._root / "logs"

    def resolve(self, candidate: str | Path) -> Path:
        path = Path(candidate).expanduser()
        if path.is_absolute():
            return path
        return (self._root / path).resolve()
