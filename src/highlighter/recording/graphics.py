from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config.schema import GameConfig, RecordingConfig
from ..game.installation import Cs2Installation
from ..infrastructure.logging import get_logger

LEGACY_BACKUP_SUFFIX = ".highlighter-backup"
PRESET_FILE_NAME = "graphics_preset.json"
PRESET_VERSION = 1
SETTING_TEMPLATE = '"{key}"\t\t"{value}"'

HIGH_QUALITY_SETTINGS: dict[str, str] = {
    "Autoconfig": "0",
    "setting.cpu_level": "3",
    "setting.gpu_level": "3",
    "setting.gpu_mem_level": "3",
    "setting.shaderquality": "1",
    "setting.r_texturefilteringquality": "5",
    "setting.msaa_samples": "8",
    "setting.r_csgo_cmaa_enable": "0",
    "setting.videocfg_shadow_quality": "2",
    "setting.videocfg_dynamic_shadows": "2",
    "setting.videocfg_texture_detail": "2",
    "setting.videocfg_particle_detail": "2",
    "setting.videocfg_ao_detail": "2",
    "setting.videocfg_hdr_detail": "3",
    "setting.videocfg_fsr_detail": "0",
    "setting.mat_vsync": "0",
    "setting.r_low_latency": "0",
    "setting.high_dpi": "0",
    "setting.nowindowborder": "1",
}


@dataclass(frozen=True, slots=True)
class SettingChange:
    file: str
    key: str
    original: str
    applied: str

    def to_mapping(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "key": self.key,
            "original": self.original,
            "applied": self.applied,
        }

    @classmethod
    def from_mapping(cls, source: dict[str, Any]) -> "SettingChange | None":
        try:
            return cls(
                file=str(source["file"]),
                key=str(source["key"]),
                original=str(source["original"]),
                applied=str(source["applied"]),
            )
        except (KeyError, TypeError, ValueError):
            return None


class GraphicsProfile:
    def __init__(
        self,
        installation: Cs2Installation,
        recording: RecordingConfig,
        game: GameConfig,
        state_directory: Path | None = None,
    ) -> None:
        self._installation = installation
        self._recording = recording
        self._game = game
        self._state_file = (state_directory or Path(".")) / PRESET_FILE_NAME
        self._logger = get_logger("recording.graphics")

    @property
    def state_file(self) -> Path:
        return self._state_file

    def apply(self) -> None:
        if not self._game.apply_high_graphics:
            return

        self.restore()
        changes: list[SettingChange] = []
        for settings_file in self._installation.video_settings_files():
            if settings_file.is_file():
                changes.extend(self._rewrite(settings_file))

        if not changes:
            return

        self._remember(changes)
        self._logger.info(
            "Changed %d video setting(s) at %dx%d, the rest of your settings were left alone",
            len(changes),
            self._recording.width,
            self._recording.height,
        )

    def restore(self) -> int:
        self._restore_legacy_backups()
        changes = self._recall()
        if not changes:
            return 0
        if not self._game.restore_graphics_on_exit:
            self._state_file.unlink(missing_ok=True)
            return 0

        restored = 0
        for settings_file, grouped in self._by_file(changes).items():
            restored += self._put_back(settings_file, grouped)

        self._state_file.unlink(missing_ok=True)
        if restored:
            self._logger.info("Put %d video setting(s) back", restored)
        return restored

    def _put_back(self, settings_file: Path, changes: list[SettingChange]) -> int:
        if not settings_file.is_file():
            return 0

        content = settings_file.read_text(encoding="utf-8", errors="ignore")
        restored = 0
        for change in changes:
            current = self._read_setting(content, change.key)
            if current is None or current != change.applied:
                continue
            updated = self._replace_existing_setting(content, change.key, change.original)
            if updated is None:
                continue
            content = updated
            restored += 1

        if restored:
            settings_file.write_text(content, encoding="utf-8")
        return restored

    def _rewrite(self, settings_file: Path) -> list[SettingChange]:
        content = settings_file.read_text(encoding="utf-8", errors="ignore")
        changes: list[SettingChange] = []

        for key, value in self._desired_settings().items():
            original = self._read_setting(content, key)
            if original is None or original == value:
                continue
            updated = self._replace_existing_setting(content, key, value)
            if updated is None:
                continue
            content = updated
            changes.append(
                SettingChange(
                    file=str(settings_file), key=key, original=original, applied=value
                )
            )

        if changes:
            settings_file.write_text(content, encoding="utf-8")
            self._logger.debug("Applied %d settings to %s", len(changes), settings_file)
        return changes

    def _desired_settings(self) -> dict[str, str]:
        settings = dict(HIGH_QUALITY_SETTINGS)
        settings["setting.defaultres"] = str(self._recording.width)
        settings["setting.defaultresheight"] = str(self._recording.height)
        settings["setting.fullscreen"] = "1" if self._recording.fullscreen else "0"
        return settings

    def _remember(self, changes: list[SettingChange]) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": PRESET_VERSION,
            "changes": [change.to_mapping() for change in changes],
        }
        self._state_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def _recall(self) -> list[SettingChange]:
        if not self._state_file.is_file():
            return []
        try:
            raw = json.loads(self._state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._state_file.unlink(missing_ok=True)
            return []
        if not isinstance(raw, dict) or int(raw.get("version") or 0) != PRESET_VERSION:
            self._state_file.unlink(missing_ok=True)
            return []

        collected: list[SettingChange] = []
        for entry in raw.get("changes") or []:
            if not isinstance(entry, dict):
                continue
            change = SettingChange.from_mapping(entry)
            if change is not None:
                collected.append(change)
        return collected

    def _restore_legacy_backups(self) -> None:
        for settings_file in self._installation.video_settings_files():
            backup = settings_file.with_name(settings_file.name + LEGACY_BACKUP_SUFFIX)
            if not backup.is_file():
                continue
            if self._game.restore_graphics_on_exit and settings_file.is_file():
                settings_file.write_bytes(backup.read_bytes())
                self._logger.info("Restored %s from an older backup", settings_file.name)
            backup.unlink(missing_ok=True)

    @staticmethod
    def _by_file(changes: list[SettingChange]) -> dict[Path, list[SettingChange]]:
        grouped: dict[Path, list[SettingChange]] = {}
        for change in changes:
            grouped.setdefault(Path(change.file), []).append(change)
        return grouped

    @staticmethod
    def _read_setting(content: str, key: str) -> str | None:
        found = re.search(rf'"{re.escape(key)}"\s*"([^"]*)"', content)
        return found.group(1) if found is not None else None

    @staticmethod
    def _replace_existing_setting(content: str, key: str, value: str) -> str | None:
        pattern = re.compile(rf'"{re.escape(key)}"\s*"[^"]*"')
        if not pattern.search(content):
            return None
        return pattern.sub(SETTING_TEMPLATE.format(key=key, value=value), content, count=1)
