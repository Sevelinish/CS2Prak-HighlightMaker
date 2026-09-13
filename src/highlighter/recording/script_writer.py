from __future__ import annotations

from pathlib import Path

from ..infrastructure.errors import RecordingError
from ..infrastructure.logging import get_logger
from .mirv_script import ScriptBundle

SCRIPT_PREFIX = "highlighter_"


class ScriptWriter:
    def __init__(self, config_directory: Path, mirror_directory: Path | None = None) -> None:
        self._config_directory = config_directory
        self._mirror_directory = mirror_directory
        self._written: list[Path] = []
        self._logger = get_logger("recording.scripts")

    def write(self, bundle: ScriptBundle) -> list[Path]:
        if not self._config_directory.is_dir():
            raise RecordingError(f"CS2 config directory is missing: {self._config_directory}")

        self.cleanup()
        for script in bundle.files:
            target = self._config_directory / script.file_name
            target.write_text(script.content, encoding="utf-8")
            self._written.append(target)
            self._mirror(script.file_name, script.content)

        self._logger.debug("Wrote %d mirv scripts to %s", len(self._written), self._config_directory)
        return list(self._written)

    def cleanup(self) -> None:
        for stale in self._config_directory.glob(f"{SCRIPT_PREFIX}*.cfg"):
            stale.unlink(missing_ok=True)
        self._written.clear()

    def _mirror(self, file_name: str, content: str) -> None:
        if self._mirror_directory is None:
            return
        self._mirror_directory.mkdir(parents=True, exist_ok=True)
        (self._mirror_directory / file_name).write_text(content, encoding="utf-8")
