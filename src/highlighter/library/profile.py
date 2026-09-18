from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..domain.team import TeamSide

UNKNOWN_MAP = ""
KEY_SEPARATOR = ":"


@dataclass(frozen=True, slots=True)
class PlayerCard:
    name: str
    steam_id64: int = 0
    side: TeamSide | None = None

    @property
    def side_label(self) -> str:
        return self.side.label if self.side is not None else ""

    def to_mapping(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "steamId64": str(self.steam_id64),
            "side": self.side_label,
        }

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "PlayerCard | None":
        name = str(source.get("name") or "").strip()
        if not name:
            return None
        return cls(
            name=name,
            steam_id64=_as_steam_id(source.get("steamId64")),
            side=TeamSide.from_label(str(source.get("side") or "")),
        )


@dataclass(frozen=True, slots=True)
class DemoProfile:
    name: str
    path: str
    size_bytes: int
    modified_at: float
    map_name: str = UNKNOWN_MAP
    server_name: str = ""
    players: tuple[PlayerCard, ...] = ()
    indexed_at: float = 0.0

    @property
    def key(self) -> str:
        return f"{self.name.lower()}{KEY_SEPARATOR}{self.size_bytes}"

    @property
    def stem(self) -> str:
        return Path(self.name).stem

    @property
    def is_readable(self) -> bool:
        return bool(self.map_name)

    @property
    def player_names(self) -> tuple[str, ...]:
        return tuple(card.name for card in self.players)

    def card_for(self, name: str) -> PlayerCard | None:
        wanted = name.strip().lower()
        for card in self.players:
            if card.name.lower() == wanted:
                return card
        return None

    def matches(self, demo_name: str) -> bool:
        wanted = demo_name.strip().lower()
        if not wanted:
            return False
        return wanted in {self.name.lower(), self.stem.lower()}

    @staticmethod
    def key_for(path: Path) -> str:
        try:
            size = path.stat().st_size
        except OSError:
            return ""
        return f"{path.name.lower()}{KEY_SEPARATOR}{size}"

    def to_mapping(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "sizeBytes": self.size_bytes,
            "modifiedAt": round(self.modified_at, 3),
            "map": self.map_name,
            "server": self.server_name,
            "players": [card.to_mapping() for card in self.players],
            "indexedAt": round(self.indexed_at, 3),
        }

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "DemoProfile | None":
        name = str(source.get("name") or "").strip()
        if not name:
            return None
        try:
            return cls(
                name=name,
                path=str(source.get("path") or ""),
                size_bytes=int(source.get("sizeBytes") or 0),
                modified_at=float(source.get("modifiedAt") or 0.0),
                map_name=str(source.get("map") or UNKNOWN_MAP),
                server_name=str(source.get("server") or ""),
                players=_as_cards(source.get("players")),
                indexed_at=float(source.get("indexedAt") or 0.0),
            )
        except (TypeError, ValueError):
            return None


def _as_cards(raw: Any) -> tuple[PlayerCard, ...]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return ()
    collected = [
        PlayerCard.from_mapping(entry) for entry in raw if isinstance(entry, Mapping)
    ]
    return tuple(card for card in collected if card is not None)


def _as_steam_id(raw: Any) -> int:
    try:
        return int(str(raw or "0"))
    except (TypeError, ValueError):
        return 0
