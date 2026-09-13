from __future__ import annotations

import re

RANGE_PATTERN = re.compile(r"^(\d+)\s*-\s*(\d+)$")
ALL_KEYWORDS = frozenset({"all", "*", "все", "всё"})
NONE_KEYWORDS = frozenset({"none", "q", "quit", "exit", "отмена", "нет"})


class SelectionParser:
    def __init__(self, maximum_index: int) -> None:
        self._maximum_index = maximum_index

    def parse(self, expression: str) -> list[int]:
        normalized = expression.strip().lower()
        if not normalized or normalized in NONE_KEYWORDS:
            return []
        if normalized in ALL_KEYWORDS:
            return list(range(1, self._maximum_index + 1))

        selected: set[int] = set()
        for token in re.split(r"[,\s]+", normalized):
            if not token:
                continue
            selected.update(self._parse_token(token))
        return sorted(selected)

    def _parse_token(self, token: str) -> set[int]:
        range_match = RANGE_PATTERN.match(token)
        if range_match:
            start, stop = int(range_match.group(1)), int(range_match.group(2))
            if start > stop:
                start, stop = stop, start
            return {value for value in range(start, stop + 1) if self._is_valid(value)}

        if token.isdigit() and self._is_valid(int(token)):
            return {int(token)}
        raise ValueError(f"Unrecognised selection token: {token}")

    def _is_valid(self, value: int) -> bool:
        return 1 <= value <= self._maximum_index
