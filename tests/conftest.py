from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from highlighter.domain.kill import Kill
from highlighter.domain.match import Match
from highlighter.domain.player import Player
from highlighter.domain.round import Round
from highlighter.domain.team import TeamSide
from highlighter.domain.weapon import Weapon

TICK_RATE = 64


def make_player(index: int, name: str | None = None) -> Player:
    return Player(steam_id64=76561197960265728 + index, name=name or f"player{index}")


def make_kill(
    tick: int,
    attacker: Player,
    victim: Player,
    round_number: int = 1,
    weapon: str = "ak47",
    attacker_side: TeamSide = TeamSide.TERRORIST,
    victim_side: TeamSide = TeamSide.COUNTER_TERRORIST,
    **flags: bool,
) -> Kill:
    return Kill(
        tick=tick,
        round_number=round_number,
        attacker=attacker,
        victim=victim,
        attacker_side=attacker_side,
        victim_side=victim_side,
        weapon=Weapon(weapon),
        headshot=flags.get("headshot", False),
        wallbang=flags.get("wallbang", False),
        noscope=flags.get("noscope", False),
        through_smoke=flags.get("through_smoke", False),
        attacker_blind=flags.get("attacker_blind", False),
        attacker_airborne=flags.get("attacker_airborne", False),
        distance=flags.get("distance", 500.0),
    )


def make_round(
    number: int = 1,
    kills: list[Kill] | None = None,
    winner: TeamSide | None = TeamSide.TERRORIST,
    roster: dict[int, TeamSide] | None = None,
    freeze_end_tick: int = 1000,
    end_tick: int = 8000,
) -> Round:
    return Round(
        number=number,
        freeze_end_tick=freeze_end_tick,
        end_tick=end_tick,
        winner=winner,
        end_reason="ct_killed",
        roster=roster or {},
        kills=kills or [],
    )


def make_roster(terrorists: list[Player], counter_terrorists: list[Player]) -> dict[int, TeamSide]:
    roster = {player.steam_id64: TeamSide.TERRORIST for player in terrorists}
    roster.update({player.steam_id64: TeamSide.COUNTER_TERRORIST for player in counter_terrorists})
    return roster


@pytest.fixture
def terrorists() -> list[Player]:
    return [make_player(index) for index in range(1, 6)]


@pytest.fixture
def counter_terrorists() -> list[Player]:
    return [make_player(index) for index in range(11, 16)]


@pytest.fixture
def match(tmp_path: Path) -> Match:
    return Match(
        demo_path=tmp_path / "sample.dem",
        map_name="de_mirage",
        tick_rate=TICK_RATE,
    )
