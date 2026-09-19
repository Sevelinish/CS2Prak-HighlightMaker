from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping

TOP_LEVEL_MESSAGE = "the file has to hold a JSON object, the outermost braces"


@dataclass(frozen=True, slots=True)
class Verdict:
    ok: bool = True
    message: str = ""
    row: int = 0
    column: int = 0

    @classmethod
    def fine(cls) -> "Verdict":
        return cls()

    @classmethod
    def wrong(cls, message: str, row: int = 0, column: int = 0) -> "Verdict":
        return cls(ok=False, message=message, row=max(0, row), column=max(0, column))


class JsonValidator:
    def __init__(self, shape: Callable[[Mapping[str, Any]], Any] | None = None) -> None:
        self._shape = shape

    def check(self, text: str) -> Verdict:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as error:
            return Verdict.wrong(
                f"{error.msg} at line {error.lineno}", error.lineno - 1, error.colno - 1
            )

        if not isinstance(parsed, dict):
            return Verdict.wrong(TOP_LEVEL_MESSAGE)
        return self._shaped(parsed)

    def _shaped(self, parsed: Mapping[str, Any]) -> Verdict:
        if self._shape is None:
            return Verdict.fine()
        try:
            self._shape(parsed)
        except (KeyError, TypeError, ValueError) as error:
            return Verdict.wrong(f"a setting has the wrong kind of value: {error}")
        return Verdict.fine()
