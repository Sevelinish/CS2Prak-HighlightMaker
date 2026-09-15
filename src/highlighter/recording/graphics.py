from __future__ import annotations

import re
from pathlib import Path

from ..config.schema import GameConfig, RecordingConfig
from ..game.installation import Cs2Installation
from ..infrastructure.logging import get_logger

BACKUP_SUFFIX = ".highlighter-backup"
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


class GraphicsProfile:
    def __init__(
        self,
        installation: Cs2Installation,
        recording: RecordingConfig,
        game: GameConfig,
    ) -> None:
        self._installation = installation
        self._recording = recording
        self._game = game
        self._logger = get_logger("recording.graphics")
        self._modified: list[Path] = []

    def apply(self) -> None:
        if not self._game.apply_high_graphics:
            return

        for settings_file in self._installation.video_settings_files():
            if not settings_file.is_file():
                continue
            self._backup(settings_file)
            applied = self._rewrite(settings_file)
            self._modified.append(settings_file)
            self._logger.debug("Applied %d settings to %s", applied, settings_file)

        if self._modified:
            self._logger.info(
                "High graphics preset applied at %dx%d",
                self._recording.width,
                self._recording.height,
            )

    def restore(self) -> None:
        if not self._game.restore_graphics_on_exit:
            self._modified.clear()
            return

        for settings_file in self._modified:
            backup = self._backup_path(settings_file)
            if backup.is_file():
                settings_file.write_bytes(backup.read_bytes())
                backup.unlink(missing_ok=True)
        self._modified.clear()

    def restore_pending(self) -> int:
        if not self._game.restore_graphics_on_exit:
            return 0

        restored = 0
        for settings_file in self._installation.video_settings_files():
            backup = self._backup_path(settings_file)
            if not backup.is_file():
                continue
            settings_file.write_bytes(backup.read_bytes())
            backup.unlink(missing_ok=True)
            restored += 1
        if restored:
            self._logger.info("Restored %d video settings file(s) from a previous run", restored)
        return restored

    def _backup(self, settings_file: Path) -> None:
        backup = self._backup_path(settings_file)
        if not backup.exists():
            backup.write_bytes(settings_file.read_bytes())

    def _rewrite(self, settings_file: Path) -> int:
        content = settings_file.read_text(encoding="utf-8", errors="ignore")
        applied = 0

        for key, value in self._desired_settings().items():
            updated = self._replace_existing_setting(content, key, value)
            if updated is not None:
                content = updated
                applied += 1

        settings_file.write_text(content, encoding="utf-8")
        return applied

    def _desired_settings(self) -> dict[str, str]:
        settings = dict(HIGH_QUALITY_SETTINGS)
        settings["setting.defaultres"] = str(self._recording.width)
        settings["setting.defaultresheight"] = str(self._recording.height)
        settings["setting.fullscreen"] = "1" if self._recording.fullscreen else "0"
        return settings

    @staticmethod
    def _replace_existing_setting(content: str, key: str, value: str) -> str | None:
        pattern = re.compile(rf'"{re.escape(key)}"\s*"[^"]*"')
        if not pattern.search(content):
            return None
        return pattern.sub(SETTING_TEMPLATE.format(key=key, value=value), content, count=1)

    @staticmethod
    def _backup_path(settings_file: Path) -> Path:
        return settings_file.with_name(settings_file.name + BACKUP_SUFFIX)
