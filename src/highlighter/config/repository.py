from __future__ import annotations

import json
from pathlib import Path

from ..infrastructure.errors import ConfigurationError
from .migrations import ConfigMigrator
from .schema import ApplicationConfig


class ConfigRepository:
    def __init__(self, config_file: Path) -> None:
        self._config_file = config_file
        self._migrated = False

    @property
    def migrated(self) -> bool:
        return self._migrated

    @property
    def config_file(self) -> Path:
        return self._config_file

    def load(self) -> ApplicationConfig:
        if not self._config_file.exists():
            config = ApplicationConfig()
            self.save(config)
            return config

        try:
            raw = json.loads(self._config_file.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as error:
            raise ConfigurationError(
                f"config.json is not valid JSON ({error.msg}, line {error.lineno})"
            ) from error

        if not isinstance(raw, dict):
            raise ConfigurationError("config.json must contain a JSON object")

        self._migrated = ConfigMigrator().migrate(raw)
        config = ApplicationConfig.from_mapping(raw)
        if self._migrated or raw != config.to_mapping():
            self.save(config)
        return config

    def save(self, config: ApplicationConfig) -> None:
        self._config_file.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(config.to_mapping(), indent=2, ensure_ascii=False)
        self._config_file.write_text(payload + "\n", encoding="utf-8")
