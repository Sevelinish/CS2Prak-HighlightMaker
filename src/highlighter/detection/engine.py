from __future__ import annotations

from collections import defaultdict

from ..config.schema import DetectionConfig
from ..domain.highlight import Highlight, HighlightTag
from ..domain.kill import Kill
from ..domain.match import Match
from ..domain.player import Player
from ..domain.round import Round
from ..infrastructure.logging import get_logger
from .context import RoundContext
from .registry import RuleRegistry


class HighlightEngine:
    def __init__(self, settings: DetectionConfig) -> None:
        self._settings = settings
        self._rules = RuleRegistry(settings).build()
        self._logger = get_logger("detection")

    def detect(self, match: Match, only_steam_id: int | None = None) -> list[Highlight]:
        pistol_rounds = self._pistol_round_numbers(match)
        detected: list[Highlight] = []

        for round_ in match.rounds:
            context = RoundContext(round_, round_.number in pistol_rounds)
            for candidate in self._candidates(round_):
                if only_steam_id is not None and candidate.player.steam_id64 != only_steam_id:
                    continue
                tags = self._collect_tags(context, candidate)
                if not tags:
                    continue
                scored = candidate.with_tags(tags)
                if scored.score >= self._settings.minimum_score:
                    detected.append(scored)

        detected.sort(key=lambda item: (-item.score, item.round_number))
        limited = detected[: self._settings.maximum_highlights]
        self._logger.debug(
            "Detected %d highlights (%d before limit) across %d rounds",
            len(limited),
            len(detected),
            match.round_count,
        )
        return limited

    def _candidates(self, round_: Round) -> list[Highlight]:
        grouped: dict[int, list[Kill]] = defaultdict(list)
        owners: dict[int, Player] = {}

        for kill in round_.kills:
            if not self._is_enemy_kill(round_, kill):
                continue
            grouped[kill.attacker.steam_id64].append(kill)
            owners[kill.attacker.steam_id64] = kill.attacker

        return [
            Highlight(
                round_number=round_.number,
                player=owners[steam_id],
                side=round_.side_of(steam_id),
                kills=tuple(kills),
            )
            for steam_id, kills in grouped.items()
            if len(kills) >= self._settings.minimum_kills
        ]

    @staticmethod
    def _is_enemy_kill(round_: Round, kill: Kill) -> bool:
        if kill.attacker.steam_id64 == kill.victim.steam_id64:
            return False
        attacker_side = kill.attacker_side or round_.side_of(kill.attacker.steam_id64)
        victim_side = kill.victim_side or round_.side_of(kill.victim.steam_id64)
        if attacker_side is None or victim_side is None:
            return True
        return attacker_side is not victim_side

    def _collect_tags(
        self, context: RoundContext, candidate: Highlight
    ) -> tuple[HighlightTag, ...]:
        collected: dict[str, HighlightTag] = {}
        for rule in self._rules:
            for tag in rule.evaluate(context, candidate):
                existing = collected.get(tag.code)
                if existing is None or tag.weight > existing.weight:
                    collected[tag.code] = tag
        return tuple(collected.values())

    @staticmethod
    def _pistol_round_numbers(match: Match) -> set[int]:
        if not match.rounds:
            return set()

        pistol_rounds = {match.rounds[0].number}
        opening_roster = match.rounds[0].roster
        if not opening_roster:
            return pistol_rounds

        for round_ in match.rounds[1:]:
            if not round_.roster:
                continue
            swapped = any(
                round_.roster.get(steam_id) is not None
                and round_.roster[steam_id] is not side
                for steam_id, side in opening_roster.items()
            )
            if swapped:
                pistol_rounds.add(round_.number)
                break
        return pistol_rounds
