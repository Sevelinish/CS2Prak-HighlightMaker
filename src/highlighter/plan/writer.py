from __future__ import annotations

import json
from pathlib import Path

from .models import RecordingPlan


class RecordingPlanWriter:
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def write(self, plan: RecordingPlan) -> Path:
        self._directory.mkdir(parents=True, exist_ok=True)
        destination = self._directory / f"{plan.demo_name}.json"
        payload = json.dumps(plan.to_mapping(), indent=2, ensure_ascii=False)
        destination.write_text(payload + "\n", encoding="utf-8")
        return destination
