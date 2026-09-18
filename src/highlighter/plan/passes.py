from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

FIRST_PASS = 1


@dataclass(frozen=True, slots=True)
class PassSlot:
    start_tick: int
    end_tick: int

    def clashes_with(self, other: "PassSlot", margin: int) -> bool:
        return other.start_tick - margin <= self.end_tick


class PassPlanner:
    def __init__(self, margin_ticks: int = 0) -> None:
        self._margin = max(0, margin_ticks)

    def assign(self, slots: Sequence[PassSlot], reserved: int = 0) -> list[int]:
        assigned = [FIRST_PASS] * len(slots)
        last_in_pass: dict[int, PassSlot] = {}

        for index in self._in_time_order(range(min(reserved, len(slots))), slots):
            assigned[index] = FIRST_PASS
            last_in_pass[FIRST_PASS] = slots[index]

        for index in self._in_time_order(range(reserved, len(slots)), slots):
            number = self._lowest_free(slots[index], last_in_pass)
            assigned[index] = number
            last_in_pass[number] = slots[index]
        return assigned

    @staticmethod
    def _in_time_order(indexes, slots: Sequence[PassSlot]) -> list[int]:
        return sorted(indexes, key=lambda index: slots[index].start_tick)

    def _lowest_free(self, slot: PassSlot, last_in_pass: dict[int, PassSlot]) -> int:
        number = FIRST_PASS
        while True:
            taken = last_in_pass.get(number)
            if taken is None or not taken.clashes_with(slot, self._margin):
                return number
            number += 1
