from __future__ import annotations

import zipfile
from pathlib import Path

from ..infrastructure.errors import ToolchainError


class ArchiveExtractor:
    def extract(self, archive: Path, destination: Path) -> Path:
        if not zipfile.is_zipfile(archive):
            raise ToolchainError(f"{archive.name} is not a valid zip archive")

        destination.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                self._guard_against_traversal(member.filename, destination)
            bundle.extractall(destination)
        return destination

    @staticmethod
    def find_executable(root: Path, executable_name: str) -> Path | None:
        direct = root / executable_name
        if direct.is_file():
            return direct
        for candidate in root.rglob(executable_name):
            if candidate.is_file():
                return candidate
        return None

    @staticmethod
    def _guard_against_traversal(member_name: str, destination: Path) -> None:
        resolved = (destination / member_name).resolve()
        if not resolved.is_relative_to(destination.resolve()):
            raise ToolchainError(f"Archive contains an unsafe path: {member_name}")
