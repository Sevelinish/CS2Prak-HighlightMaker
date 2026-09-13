from __future__ import annotations

from ..domain.match import Match
from ..domain.player import Player
from ..infrastructure.errors import HighlighterError

STEAM_ID64_LENGTH = 17


class PlayerNotFoundError(HighlighterError):
    pass


class PlayerResolver:
    def __init__(self, match: Match) -> None:
        self._match = match

    def resolve(self, query: str) -> Player:
        cleaned = query.strip()
        if not cleaned:
            raise PlayerNotFoundError("No player name given")

        by_id = self._by_steam_id(cleaned)
        if by_id is not None:
            return by_id

        exact = self._matching(lambda name: name == cleaned.lower())
        if len(exact) == 1:
            return exact[0]

        partial = self._matching(lambda name: cleaned.lower() in name)
        if len(partial) == 1:
            return partial[0]
        if len(partial) > 1:
            names = ", ".join(sorted(player.name for player in partial))
            raise PlayerNotFoundError(f"'{cleaned}' matches several players: {names}")

        raise PlayerNotFoundError(
            f"No player called '{cleaned}' in this demo. Players: {self._roster()}"
        )

    def _by_steam_id(self, query: str) -> Player | None:
        if not query.isdigit() or len(query) != STEAM_ID64_LENGTH:
            return None
        player = self._match.players.get(int(query))
        if player is None:
            raise PlayerNotFoundError(
                f"SteamID {query} is not in this demo. Players: {self._roster()}"
            )
        return player

    def _matching(self, predicate) -> list[Player]:
        return [player for player in self._match.players.values() if predicate(player.name.lower())]

    def _roster(self) -> str:
        return ", ".join(sorted(player.name for player in self._match.players.values()))
