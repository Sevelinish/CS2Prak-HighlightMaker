from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..infrastructure.logging import get_logger
from .archives import DemoFile

LEDGER_VERSION = 1
LEDGER_FILE_NAME = "imported_demos.json"


@dataclass(frozen=True, slots=True)
class ImportRecord:
    key: str
    source: str
    imported_as: str
    map_name: str
    imported_at: float

    def to_mapping(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "source": self.source,
            "importedAs": self.imported_as,
            "map": self.map_name,
            "importedAt": round(self.imported_at, 3),
        }

    @classmethod
    def from_mapping(cls, source: dict[str, Any]) -> "ImportRecord | None":
        try:
            return cls(
                key=str(source["key"]),
                source=str(source["source"]),
                imported_as=str(source["importedAs"]),
                map_name=str(source.get("map") or ""),
                imported_at=float(source.get("importedAt") or 0.0),
            )
        except (KeyError, TypeError, ValueError):
            return None


class ImportLedger:
    def __init__(self, work_directory: Path) -> None:
        self._file = work_directory / LEDGER_FILE_NAME
        self._records: dict[str, ImportRecord] = {}
        self._logger = get_logger("importing.ledger")
        self._load()

    @property
    def file(self) -> Path:
        return self._file

    @staticmethod
    def key_for(demo: DemoFile) -> str:
        return f"{demo.path.name.lower()}:{demo.size_bytes}"

    def knows(self, demo: DemoFile) -> bool:
        return self.key_for(demo) in self._records

    def record_for(self, demo: DemoFile) -> ImportRecord | None:
        return self._records.get(self.key_for(demo))

    def remember(self, demo: DemoFile, imported_as: str, map_name: str, when: float) -> None:
        record = ImportRecord(
            key=self.key_for(demo),
            source=str(demo.path),
            imported_as=imported_as,
            map_name=map_name,
            imported_at=when,
        )
        self._records[record.key] = record
        self._save()

    def _load(self) -> None:
        if not self._file.is_file():
            return
        try:
            raw = json.loads(self._file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, dict) or int(raw.get("version") or 0) != LEDGER_VERSION:
            return

        for entry in raw.get("demos") or []:
            if not isinstance(entry, dict):
                continue
            record = ImportRecord.from_mapping(entry)
            if record is not None:
                self._records[record.key] = record

    def _save(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": LEDGER_VERSION,
            "demos": [record.to_mapping() for record in self._records.values()],
        }
        self._file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        self._logger.debug("Import ledger holds %d demo(s)", len(self._records))
