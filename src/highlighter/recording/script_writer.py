from __future__ import annotations

from pathlib import Path

from ..infrastructure.errors import RecordingError
from ..infrastructure.logging import get_logger
from .mirv_script import ScriptBundle

SCRIPT_PREFIX = "highlighter_"
CLEANED_PATTERNS = (f"{SCRIPT_PREFIX}*.cfg", f"{SCRIPT_PREFIX}*.xml")


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
        for script in self._ordered(bundle):
            target = self._config_directory / script.file_name
            target.write_text(script.content, encoding="utf-8")
            self._written.append(target)
            self._mirror(script.file_name, script.content)

        self._logger.debug("Wrote %d mirv scripts to %s", len(self._written), self._config_directory)
        return list(self._written)

    @staticmethod
    def _ordered(bundle: ScriptBundle) -> list:
        if not bundle.hands_over:
            return list(bundle.files)
        others = [item for item in bundle.files if item.name != bundle.handover_script]
        handover = [item for item in bundle.files if item.name == bundle.handover_script]
        return others + handover

    def replace(self, script_name: str, content: str) -> Path:
        target = self._config_directory / f"{script_name}.cfg"
        target.write_text(content, encoding="utf-8")
        if target not in self._written:
            self._written.append(target)
        self._mirror(target.name, content)
        self._logger.debug("Rewrote %s", target.name)
        return target

    def drop(self, script_name: str) -> bool:
        target = self._config_directory / f"{script_name}.cfg"
        if not target.is_file():
            return False
        target.unlink(missing_ok=True)
        if target in self._written:
            self._written.remove(target)
        self._logger.debug("Dropped %s", target.name)
        return True

    def cleanup(self) -> None:
        for pattern in CLEANED_PATTERNS:
            for stale in self._config_directory.glob(pattern):
                stale.unlink(missing_ok=True)
        self._written.clear()

    def _mirror(self, file_name: str, content: str) -> None:
        if self._mirror_directory is None:
            return
        self._mirror_directory.mkdir(parents=True, exist_ok=True)
        (self._mirror_directory / file_name).write_text(content, encoding="utf-8")
