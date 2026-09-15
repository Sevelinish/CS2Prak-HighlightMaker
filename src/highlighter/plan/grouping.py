from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, TypeVar

Item = TypeVar("Item")


@dataclass(frozen=True, slots=True)
class Window:
    start: int
    end: int

    def touches(self, other: "Window") -> bool:
        return other.start <= self.end and self.start <= other.end

    def merged(self, other: "Window") -> "Window":
        return Window(min(self.start, other.start), max(self.end, other.end))


class OverlapGrouper:
    @staticmethod
    def group(
        items: Iterable[Item], window_of: Callable[[Item], Window]
    ) -> list[list[Item]]:
        ordered = sorted(items, key=lambda item: window_of(item).start)
        groups: list[list[Item]] = []
        span: Window | None = None

        for item in ordered:
            window = window_of(item)
            if span is not None and span.touches(window):
                groups[-1].append(item)
                span = span.merged(window)
                continue
            groups.append([item])
            span = window
        return groups

    @staticmethod
    def merged_count(groups: list[list[Item]]) -> int:
        return sum(len(group) - 1 for group in groups if len(group) > 1)
