from __future__ import annotations

import time
from pathlib import Path

from ..domain.match import Match
from ..domain.team import TeamSide
from ..infrastructure.logging import get_logger
from .profile import DemoProfile, PlayerCard

STEAM_ID_COLUMN = "steamid"
NAME_COLUMN = "name"
TEAM_COLUMN = "team_number"
BOT_STEAM_ID = 0


class DemoProfiler:
    def __init__(self) -> None:
        self._logger = get_logger("library")

    def profile(self, demo: Path) -> DemoProfile:
        stamp = self._stamp(demo)
        try:
            from demoparser2 import DemoParser

            parser = DemoParser(str(demo))
            header = parser.parse_header()
            players = self._players(parser)
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as error:
            self._logger.warning("Could not read %s: %s", demo.name, error)
            return stamp

        self._logger.debug(
            "Indexed %s: %s, %d player(s)",
            demo.name,
            header.get("map_name"),
            len(players),
        )
        return DemoProfile(
            name=stamp.name,
            path=stamp.path,
            size_bytes=stamp.size_bytes,
            modified_at=stamp.modified_at,
            map_name=str(header.get("map_name") or ""),
            server_name=str(header.get("server_name") or ""),
            players=players,
            indexed_at=stamp.indexed_at,
        )

    def from_match(self, match: Match) -> DemoProfile:
        stamp = self._stamp(match.demo_path)
        return DemoProfile(
            name=stamp.name,
            path=stamp.path,
            size_bytes=stamp.size_bytes,
            modified_at=stamp.modified_at,
            map_name=match.map_name,
            server_name=match.server_name,
            players=self._from_match(match),
            indexed_at=stamp.indexed_at,
        )

    def _players(self, parser) -> tuple[PlayerCard, ...]:
        table = parser.parse_player_info()
        if table is None or table.empty:
            return ()

        collected: list[PlayerCard] = []
        seen: set[int] = set()
        for row in table.to_dict("records"):
            card = self._card(row)
            if card is None or card.steam_id64 in seen:
                continue
            seen.add(card.steam_id64)
            collected.append(card)
        return tuple(collected)

    @staticmethod
    def _card(row: dict) -> PlayerCard | None:
        name = str(row.get(NAME_COLUMN) or "").strip()
        if not name:
            return None
        try:
            steam_id = int(str(row.get(STEAM_ID_COLUMN) or BOT_STEAM_ID))
        except (TypeError, ValueError):
            steam_id = BOT_STEAM_ID
        if steam_id == BOT_STEAM_ID:
            return None
        return PlayerCard(
            name=name,
            steam_id64=steam_id,
            side=TeamSide.from_team_number(row.get(TEAM_COLUMN)),
        )

    @staticmethod
    def _from_match(match: Match) -> tuple[PlayerCard, ...]:
        roster = match.rounds[0].roster if match.rounds else {}
        return tuple(
            PlayerCard(
                name=player.name,
                steam_id64=player.steam_id64,
                side=roster.get(player.steam_id64),
            )
            for player in match.players.values()
        )

    @staticmethod
    def _stamp(demo: Path) -> DemoProfile:
        try:
            stats = demo.stat()
            size, modified = stats.st_size, stats.st_mtime
        except OSError:
            size, modified = 0, 0.0
        return DemoProfile(
            name=demo.name,
            path=str(demo),
            size_bytes=size,
            modified_at=modified,
            indexed_at=time.time(),
        )
