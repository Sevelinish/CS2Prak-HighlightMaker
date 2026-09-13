from __future__ import annotations

from conftest import make_kill, make_roster, make_round

from highlighter.detection.context import RoundContext
from highlighter.domain.team import TeamSide


def test_detects_won_one_versus_three(terrorists, counter_terrorists):
    hero = terrorists[0]
    kills = [
        make_kill(1100, counter_terrorists[0], terrorists[1],
                  attacker_side=TeamSide.COUNTER_TERRORIST, victim_side=TeamSide.TERRORIST),
        make_kill(1200, counter_terrorists[0], terrorists[2],
                  attacker_side=TeamSide.COUNTER_TERRORIST, victim_side=TeamSide.TERRORIST),
        make_kill(1300, counter_terrorists[1], terrorists[3],
                  attacker_side=TeamSide.COUNTER_TERRORIST, victim_side=TeamSide.TERRORIST),
        make_kill(1400, counter_terrorists[1], terrorists[4],
                  attacker_side=TeamSide.COUNTER_TERRORIST, victim_side=TeamSide.TERRORIST),
        make_kill(1500, hero, counter_terrorists[0]),
        make_kill(1600, hero, counter_terrorists[1]),
        make_kill(1700, hero, counter_terrorists[2]),
        make_kill(1800, hero, counter_terrorists[3]),
        make_kill(1900, hero, counter_terrorists[4]),
    ]
    round_ = make_round(
        kills=kills,
        winner=TeamSide.TERRORIST,
        roster=make_roster(terrorists, counter_terrorists),
    )

    situation = RoundContext(round_, is_pistol_round=False).clutch_of(hero.steam_id64)

    assert situation is not None
    assert situation.opponents == 5
    assert situation.won is True


def test_lost_clutch_is_marked_as_not_won(terrorists, counter_terrorists):
    hero = terrorists[0]
    kills = [
        make_kill(1100 + offset * 100, counter_terrorists[0], victim,
                  attacker_side=TeamSide.COUNTER_TERRORIST, victim_side=TeamSide.TERRORIST)
        for offset, victim in enumerate(terrorists[1:])
    ]
    kills.append(
        make_kill(1600, counter_terrorists[0], hero,
                  attacker_side=TeamSide.COUNTER_TERRORIST, victim_side=TeamSide.TERRORIST)
    )
    round_ = make_round(
        kills=kills,
        winner=TeamSide.COUNTER_TERRORIST,
        roster=make_roster(terrorists, counter_terrorists),
    )

    situation = RoundContext(round_, is_pistol_round=False).clutch_of(hero.steam_id64)

    assert situation is not None
    assert situation.won is False


def test_one_versus_one_is_not_a_clutch(terrorists, counter_terrorists):
    hero = terrorists[0]
    kills = [
        make_kill(1100 + offset * 100, counter_terrorists[0], victim,
                  attacker_side=TeamSide.COUNTER_TERRORIST, victim_side=TeamSide.TERRORIST)
        for offset, victim in enumerate(terrorists[1:])
    ]
    kills.extend(
        make_kill(2000 + offset * 100, hero, victim)
        for offset, victim in enumerate(counter_terrorists[1:])
    )
    round_ = make_round(
        kills=kills,
        winner=TeamSide.TERRORIST,
        roster=make_roster(terrorists[:1] + terrorists[1:], counter_terrorists[:2]),
    )

    situation = RoundContext(round_, is_pistol_round=False).clutch_of(hero.steam_id64)

    assert situation is None or situation.opponents >= 2


def test_missing_roster_disables_clutch_detection(terrorists, counter_terrorists):
    round_ = make_round(
        kills=[make_kill(1100, terrorists[0], counter_terrorists[0])],
        roster={},
    )

    assert RoundContext(round_, is_pistol_round=False).clutch_of(terrorists[0].steam_id64) is None
