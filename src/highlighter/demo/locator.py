from __future__ import annotations

from pathlib import Path

DEMO_SUFFIX = ".dem"


class DemoLocator:
    def __init__(self, search_directories: list[Path]) -> None:
        self._search_directories = search_directories

    def discover(self) -> list[Path]:
        found: dict[str, Path] = {}
        for directory in self._search_directories:
            if not directory.is_dir():
                continue
            for candidate in sorted(directory.rglob(f"*{DEMO_SUFFIX}")):
                if candidate.is_file():
                    found.setdefault(str(candidate.resolve()).lower(), candidate)
        return sorted(found.values(), key=lambda path: path.stat().st_mtime, reverse=True)

    def find_by_name(self, name: str) -> Path | None:
        wanted = {name.lower(), f"{name.lower()}{DEMO_SUFFIX}"}
        for candidate in self.discover():
            if candidate.name.lower() in wanted:
                return candidate
        return None

    @property
    def search_directories(self) -> list[Path]:
        return list(self._search_directories)

    @staticmethod
    def is_demo(path: Path) -> bool:
        return path.is_file() and path.suffix.lower() == DEMO_SUFFIX
