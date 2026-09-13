from __future__ import annotations

from dataclasses import dataclass

STEAM_ID64_BASE = 76561197960265728


UNKNOWN_SLOT = 0


@dataclass(frozen=True, slots=True)
class Player:
    steam_id64: int
    name: str
    slot: int = UNKNOWN_SLOT

    @property
    def account_id(self) -> int:
        return self.steam_id64 - STEAM_ID64_BASE

    @property
    def has_slot(self) -> bool:
        return self.slot > UNKNOWN_SLOT

    def with_slot(self, slot: int) -> "Player":
        return Player(steam_id64=self.steam_id64, name=self.name, slot=slot)

    def __str__(self) -> str:
        return self.name
