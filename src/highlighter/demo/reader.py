from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd
from demoparser2 import DemoParser

from ..domain.kill import Kill
from ..domain.match import Match
from ..domain.player import Player
from ..domain.round import Round
from ..domain.team import TeamSide
from ..domain.weapon import Weapon
from ..infrastructure.errors import DemoParsingError
from ..infrastructure.logging import get_logger
from .timeline import MatchStartResolver

ROSTER_PROPERTIES = ["team_num", "is_alive"]
SLOT_PROPERTY = "user_id"
SLOT_OFFSET = 1
FALLBACK_ROUND_SECONDS = 115


class DemoReader:
    def __init__(self, demo_path: Path, tick_rate: int) -> None:
        self._demo_path = demo_path
        self._tick_rate = tick_rate
        self._logger = get_logger("demo")
        self._match_start_tick = 0

    def read(self) -> Match:
        if not self._demo_path.is_file():
            raise DemoParsingError(f"Demo file does not exist: {self._demo_path}")

        parser, header, events = self._parse_source()
        self._match_start_tick = MatchStartResolver(parser).resolve()
        match = Match(
            demo_path=self._demo_path,
            map_name=str(header.get("map_name", "unknown")),
            tick_rate=self._tick_rate,
            server_name=str(header.get("server_name", "")),
        )

        boundaries = self._build_round_boundaries(events)
        if not boundaries:
            raise DemoParsingError(f"No playable rounds found in {self._demo_path.name}")

        rosters = self._read_rosters(parser, [item.freeze_end_tick for item in boundaries])
        for boundary in boundaries:
            match.rounds.append(
                Round(
                    number=boundary.number,
                    freeze_end_tick=boundary.freeze_end_tick,
                    end_tick=boundary.end_tick,
                    winner=boundary.winner,
                    end_reason=boundary.end_reason,
                    roster=rosters.get(boundary.freeze_end_tick, {}),
                )
            )

        self._attach_kills(match, events["deaths"])
        self._attach_slots(match, parser, boundaries[0].freeze_end_tick)
        self._logger.debug(
            "Parsed %s: %d rounds, %d players",
            self._demo_path.name,
            match.round_count,
            len(match.players),
        )
        return match

    def _parse_source(self) -> tuple[DemoParser, dict, dict[str, pd.DataFrame]]:
        try:
            parser = DemoParser(str(self._demo_path))
            header = parser.parse_header()
            events = {
                "deaths": parser.parse_event(
                    "player_death",
                    player=["team_num"],
                    other=["total_rounds_played", "is_warmup_period"],
                ),
                "freeze_ends": parser.parse_event(
                    "round_freeze_end", other=["total_rounds_played", "is_warmup_period"]
                ),
                "round_ends": parser.parse_event(
                    "round_end", other=["total_rounds_played", "is_warmup_period"]
                ),
                "official_ends": parser.parse_event(
                    "round_officially_ended", other=["total_rounds_played", "is_warmup_period"]
                ),
            }
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as error:
            raise DemoParsingError(f"Failed to parse {self._demo_path.name}: {error}") from error
        return parser, header, events

    def _build_round_boundaries(self, events: dict[str, pd.DataFrame]) -> list["RoundBoundary"]:
        live_freeze = self._drop_warmup(events["freeze_ends"])
        if live_freeze.empty:
            return []

        starts = sorted({int(tick) for tick in live_freeze["tick"].tolist()})
        played_rounds = self._played_round_numbers(events["deaths"])
        outcomes = self._round_outcomes(events["round_ends"])
        stops = sorted({int(tick) for tick in self._drop_warmup(events["official_ends"])["tick"]})

        boundaries: list[RoundBoundary] = []
        for index, start_tick in enumerate(starts):
            next_start = starts[index + 1] if index + 1 < len(starts) else None
            end_tick = self._first_between(stops, start_tick, next_start)
            if end_tick is None:
                end_tick = (
                    next_start - 1
                    if next_start is not None
                    else start_tick + self._tick_rate * FALLBACK_ROUND_SECONDS
                )
            played = played_rounds[index] if index < len(played_rounds) else index
            winner, reason = outcomes.get(played, (None, None))
            boundaries.append(
                RoundBoundary(
                    number=played + 1,
                    freeze_end_tick=start_tick,
                    end_tick=end_tick,
                    winner=winner,
                    end_reason=reason,
                )
            )
        return boundaries

    @staticmethod
    def _first_between(values: list[int], lower: int, upper: int | None) -> int | None:
        for value in values:
            if value <= lower:
                continue
            if upper is not None and value >= upper:
                break
            return value
        return None

    def _played_round_numbers(self, deaths: pd.DataFrame) -> list[int]:
        live = self._drop_warmup(deaths)
        if live.empty:
            return []
        return sorted({int(value) for value in live["total_rounds_played"].tolist()})

    @staticmethod
    def _round_outcomes(round_ends: pd.DataFrame) -> dict[int, tuple[TeamSide | None, str | None]]:
        outcomes: dict[int, tuple[TeamSide | None, str | None]] = {}
        if round_ends is None or round_ends.empty:
            return outcomes
        for record in round_ends.to_dict("records"):
            winner = TeamSide.from_label(record.get("winner"))
            number = record.get("total_rounds_played")
            if winner is None or pd.isna(number):
                continue
            reason = record.get("reason")
            outcomes[int(number) - 1] = (winner, None if pd.isna(reason) else str(reason))
        return outcomes

    def _drop_warmup(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame is None or frame.empty:
            return pd.DataFrame(columns=["tick"])
        live = frame
        if "is_warmup_period" in live.columns:
            live = live[~live["is_warmup_period"].fillna(False).astype(bool)]
        if "tick" in live.columns:
            live = live[live["tick"] >= self._match_start_tick]
        return live.copy()

    def _read_rosters(self, parser: DemoParser, ticks: list[int]) -> dict[int, dict[int, TeamSide]]:
        if not ticks:
            return {}
        try:
            frame = parser.parse_ticks(ROSTER_PROPERTIES, ticks=ticks)
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as error:
            self._logger.warning("Roster lookup failed, clutch detection disabled: %s", error)
            return {}

        rosters: dict[int, dict[int, TeamSide]] = {tick: {} for tick in ticks}
        for record in frame.to_dict("records"):
            steam_id = self._as_steam_id(record.get("steamid"))
            side = TeamSide.from_team_number(record.get("team_num"))
            tick = record.get("tick")
            if steam_id is None or side is None or pd.isna(tick):
                continue
            rosters.setdefault(int(tick), {})[steam_id] = side
        return rosters

    def _attach_slots(self, match: Match, parser: DemoParser, sample_tick: int) -> None:
        slots = self._read_slots(parser, sample_tick)
        if not slots:
            self._logger.warning(
                "Demo exposes no %s property, the camera cannot be aimed by slot", SLOT_PROPERTY
            )
            return

        for steam_id, player in list(match.players.items()):
            slot = slots.get(steam_id)
            if slot is not None:
                match.players[steam_id] = player.with_slot(slot)

        for round_ in match.rounds:
            round_.kills = [self._kill_with_slots(kill, match) for kill in round_.kills]

        self._logger.debug("Resolved spectator slots for %d players", len(slots))

    def _read_slots(self, parser: DemoParser, sample_tick: int) -> dict[int, int]:
        try:
            frame = parser.parse_ticks([SLOT_PROPERTY], ticks=[sample_tick])
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as error:
            self._logger.warning("Slot lookup failed: %s", error)
            return {}

        if frame is None or frame.empty or SLOT_PROPERTY not in frame.columns:
            return {}

        slots: dict[int, int] = {}
        for record in frame.to_dict("records"):
            steam_id = self._as_steam_id(record.get("steamid"))
            user_id = record.get(SLOT_PROPERTY)
            if steam_id is None or pd.isna(user_id):
                continue
            slots[steam_id] = int(user_id) + SLOT_OFFSET
        return slots

    @staticmethod
    def _kill_with_slots(kill: Kill, match: Match) -> Kill:
        attacker = match.players.get(kill.attacker.steam_id64, kill.attacker)
        victim = match.players.get(kill.victim.steam_id64, kill.victim)
        if attacker is kill.attacker and victim is kill.victim:
            return kill
        return replace(kill, attacker=attacker, victim=victim)

    def _attach_kills(self, match: Match, deaths: pd.DataFrame) -> None:
        live = self._drop_warmup(deaths)
        if live.empty:
            return

        rounds_by_number = {round_.number: round_ for round_ in match.rounds}
        for record in live.to_dict("records"):
            attacker = self._as_player(record.get("attacker_steamid"), record.get("attacker_name"))
            victim = self._as_player(record.get("user_steamid"), record.get("user_name"))
            round_number = record.get("total_rounds_played")
            if attacker is None or victim is None or pd.isna(round_number):
                continue

            round_ = rounds_by_number.get(int(round_number) + 1)
            if round_ is None:
                continue

            match.players.setdefault(attacker.steam_id64, attacker)
            match.players.setdefault(victim.steam_id64, victim)
            round_.kills.append(self._build_kill(record, round_.number, attacker, victim))

        for round_ in match.rounds:
            round_.kills.sort(key=lambda kill: kill.tick)

    @staticmethod
    def _build_kill(record: dict, round_number: int, attacker: Player, victim: Player) -> Kill:
        return Kill(
            tick=int(record["tick"]),
            round_number=round_number,
            attacker=attacker,
            victim=victim,
            attacker_side=TeamSide.from_team_number(record.get("attacker_team_num")),
            victim_side=TeamSide.from_team_number(record.get("user_team_num")),
            weapon=Weapon(str(record.get("weapon") or "")),
            headshot=bool(record.get("headshot")),
            wallbang=DemoReader._as_int(record.get("penetrated")) > 0,
            noscope=bool(record.get("noscope")),
            through_smoke=bool(record.get("thrusmoke")),
            attacker_blind=bool(record.get("attackerblind")),
            attacker_airborne=bool(record.get("attackerinair")),
            distance=DemoReader._as_float(record.get("distance")),
        )

    @staticmethod
    def _as_player(steam_id: object, name: object) -> Player | None:
        resolved = DemoReader._as_steam_id(steam_id)
        if resolved is None:
            return None
        label = "" if name is None or (isinstance(name, float) and pd.isna(name)) else str(name)
        return Player(steam_id64=resolved, name=label or str(resolved))

    @staticmethod
    def _as_steam_id(value: object) -> int | None:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        try:
            resolved = int(value)
        except (TypeError, ValueError):
            return None
        return resolved if resolved > 0 else None

    @staticmethod
    def _as_int(value: object) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _as_float(value: object) -> float:
        try:
            resolved = float(value)
        except (TypeError, ValueError):
            return 0.0
        return 0.0 if pd.isna(resolved) else resolved


class RoundBoundary:
    __slots__ = ("number", "freeze_end_tick", "end_tick", "winner", "end_reason")

    def __init__(
        self,
        number: int,
        freeze_end_tick: int,
        end_tick: int,
        winner: TeamSide | None,
        end_reason: str | None,
    ) -> None:
        self.number = number
        self.freeze_end_tick = freeze_end_tick
        self.end_tick = end_tick
        self.winner = winner
        self.end_reason = end_reason
