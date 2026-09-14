from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ProgressReporter(Protocol):
    def begin(self, title: str) -> None: ...

    def detail(self, message: str) -> None: ...

    def done(self, note: str = "") -> None: ...

    def fail(self, note: str = "") -> None: ...


class SilentProgressReporter:
    def begin(self, title: str) -> None:
        return None

    def detail(self, message: str) -> None:
        return None

    def done(self, note: str = "") -> None:
        return None

    def fail(self, note: str = "") -> None:
        return None
