from __future__ import annotations

from pathlib import Path

import pandas as pd
from demoparser2 import DemoParser

from ..domain.geometry import Vector3, ViewAngles
from ..domain.grenade import Grenade, GrenadeKind
from ..domain.match import Match
from ..domain.player import Player
from ..infrastructure.errors import DemoParsingError
from ..infrastructure.logging import get_logger
from .callouts import CalloutAtlas
from .timeline import MatchStartResolver

PROJECTILE_COLUMN = "grenade_type"
ENTITY_COLUMN = "grenade_entity_id"
ANGLE_PROPERTIES = ["X", "Y", "Z", "pitch", "yaw"]
CALLOUT_SAMPLE_STRIDE = 64


class GrenadeReader:
    def __init__(self, demo_path: Path, match: Match, sample_stride: int = CALLOUT_SAMPLE_STRIDE) -> None:
        self._demo_path = demo_path
        self._match = match
        self._sample_stride = max(1, sample_stride)
        self._logger = get_logger("demo.grenades")

    def read(self, kinds: tuple[GrenadeKind, ...]) -> list[Grenade]:
        if not kinds:
            return []

        try:
            parser = DemoParser(str(self._demo_path))
            match_start = MatchStartResolver(parser).resolve()
            detonations = self._read_detonations(parser, kinds, match_start)
            if not detonations:
                return []
            throws = self._read_throw_ticks(parser, kinds)
            grenades = self._build(parser, detonations, throws)
        except (KeyboardInterrupt, SystemExit):
            raise
        except DemoParsingError:
            raise
        except BaseException as error:
            raise DemoParsingError(
                f"Failed to read grenades from {self._demo_path.name}: {error}"
            ) from error

        self._label_places(parser, grenades)
        grenades.sort(key=lambda item: item.throw_tick)
        self._logger.debug("Read %d grenade(s)", len(grenades))
        return grenades

    def _read_detonations(
        self, parser: DemoParser, kinds: tuple[GrenadeKind, ...], match_start: int
    ) -> list[dict]:
        collected: list[dict] = []
        for kind in kinds:
            try:
                frame = parser.parse_event(
                    kind.detonate_event, other=["total_rounds_played"]
                )
            except (KeyboardInterrupt, SystemExit):
                raise
            except BaseException as error:
                self._logger.warning("No %s events: %s", kind.detonate_event, error)
                continue

            if frame is None or frame.empty:
                continue

            for record in frame.to_dict("records"):
                tick = record.get("tick")
                if pd.isna(tick) or int(tick) < match_start:
                    continue
                record["kind"] = kind
                collected.append(record)
        return collected

    def _read_throw_ticks(
        self, parser: DemoParser, kinds: tuple[GrenadeKind, ...]
    ) -> dict[int, int]:
        try:
            trajectories = parser.parse_grenades()
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as error:
            self._logger.warning("Grenade trajectories unavailable: %s", error)
            return {}

        if trajectories is None or trajectories.empty:
            return {}

        wanted = {kind.projectile_class for kind in kinds}
        flying = trajectories[
            trajectories[PROJECTILE_COLUMN].isin(wanted) & trajectories["x"].notna()
        ]
        if flying.empty:
            return {}
        return flying.groupby(ENTITY_COLUMN)["tick"].min().astype(int).to_dict()

    def _build(
        self, parser: DemoParser, detonations: list[dict], throws: dict[int, int]
    ) -> list[Grenade]:
        resolved: list[tuple[dict, int]] = []
        for record in detonations:
            entity = record.get("entityid")
            if pd.isna(entity):
                continue
            throw_tick = throws.get(int(entity))
            if throw_tick is None:
                continue
            resolved.append((record, throw_tick))

        states = self._read_thrower_states(parser, {tick for _, tick in resolved})
        grenades: list[Grenade] = []

        for record, throw_tick in resolved:
            thrower = self._as_player(record.get("user_steamid"), record.get("user_name"))
            if thrower is None:
                continue

            state = states.get((throw_tick, thrower.steam_id64))
            if state is None:
                continue

            round_number = int(record.get("total_rounds_played", 0)) + 1
            grenades.append(
                Grenade(
                    kind=record["kind"],
                    round_number=round_number,
                    thrower=self._match.players.get(thrower.steam_id64, thrower),
                    side=self._side_in_round(round_number, thrower.steam_id64),
                    throw_tick=throw_tick,
                    detonate_tick=int(record["tick"]),
                    thrower_position=state[0],
                    thrower_angles=state[1],
                    landing=Vector3(
                        float(record["x"]), float(record["y"]), float(record["z"])
                    ),
                    round_time_seconds=self._round_time(round_number, throw_tick),
                )
            )
        return grenades

    def _read_thrower_states(
        self, parser: DemoParser, ticks: set[int]
    ) -> dict[tuple[int, int], tuple[Vector3, ViewAngles]]:
        if not ticks:
            return {}
        try:
            frame = parser.parse_ticks(ANGLE_PROPERTIES, ticks=sorted(ticks))
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as error:
            self._logger.warning("Thrower positions unavailable: %s", error)
            return {}

        states: dict[tuple[int, int], tuple[Vector3, ViewAngles]] = {}
        for record in frame.to_dict("records"):
            steam_id = record.get("steamid")
            tick = record.get("tick")
            if pd.isna(steam_id) or pd.isna(tick):
                continue
            try:
                position = Vector3(
                    float(record["X"]), float(record["Y"]), float(record["Z"])
                )
                angles = ViewAngles(float(record["pitch"]), float(record["yaw"]))
            except (KeyError, TypeError, ValueError):
                continue
            states[(int(tick), int(steam_id))] = (position, angles)
        return states

    def _label_places(self, parser: DemoParser, grenades: list[Grenade]) -> None:
        if not grenades:
            return

        lowest = min(item.throw_tick for item in grenades)
        highest = max(item.detonate_tick for item in grenades)
        ticks = list(range(lowest, highest + 1, self._sample_stride))
        atlas = CalloutAtlas.build(parser, ticks)
        if not atlas.places:
            return

        for grenade in grenades:
            grenade.landing_place = atlas.name_for(grenade.landing)

    def _side_in_round(self, round_number: int, steam_id: int):
        for round_ in self._match.rounds:
            if round_.number == round_number:
                return round_.side_of(steam_id)
        return None

    def _round_time(self, round_number: int, tick: int) -> float:
        for round_ in self._match.rounds:
            if round_.number == round_number:
                return self._match.ticks_to_seconds(max(0, tick - round_.freeze_end_tick))
        return 0.0

    @staticmethod
    def _as_player(steam_id: object, name: object) -> Player | None:
        if steam_id is None or (isinstance(steam_id, float) and pd.isna(steam_id)):
            return None
        try:
            resolved = int(steam_id)
        except (TypeError, ValueError):
            return None
        if resolved <= 0:
            return None
        label = "" if name is None or (isinstance(name, float) and pd.isna(name)) else str(name)
        return Player(steam_id64=resolved, name=label or str(resolved))
