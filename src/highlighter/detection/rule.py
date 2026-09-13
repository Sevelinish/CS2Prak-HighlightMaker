from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, Iterable

from ..config.schema import DetectionConfig
from ..domain.highlight import Highlight, HighlightTag
from .context import RoundContext


class HighlightRule(ABC):
    name: ClassVar[str] = "rule"

    def __init__(self, settings: DetectionConfig) -> None:
        self._settings = settings

    @abstractmethod
    def evaluate(self, context: RoundContext, candidate: Highlight) -> Iterable[HighlightTag]:
        raise NotImplementedError

    def _tag(self, code: str, label: str, multiplier: float = 1.0) -> HighlightTag:
        return HighlightTag(
            code=code,
            label=label,
            weight=round(self._settings.weight_of(code) * multiplier, 2),
        )
