from __future__ import annotations

import pytest
from conftest import make_kill, make_player

from highlighter.api.errors import BadRequestError
from highlighter.api.selection import (
    GrenadeSelection,
    HighlightSelection,
    SelectionCriteria,
)
from highlighter.api.serialization import Identity
from highlighter.domain.geometry import Vector3, ViewAngles
from highlighter.domain.grenade import Grenade, GrenadeKind
from highlighter.domain.highlight import Highlight, HighlightTag
from highlighter.domain.team import TeamSide

AWP = HighlightTag("awp_double", "AWP double", 8.0)
CLUTCH = HighlightTag("clutch_1v3", "clutch 1v3", 20.0)


def make_highlight(round_number: int, player, tags, weapon: str = "ak47", kills: int = 2):
    shots = tuple(
        make_kill(1000 * round_number + index, player, make_player(90 + index), weapon=weapon)
        for index in range(kills)
    )
    return Highlight(
        round_number=round_number,
        player=player,
        side=TeamSide.TERRORIST,
        kills=shots,
        tags=tags,
    )


def make_grenade(round_number: int, player, kind=GrenadeKind.SMOKE, place="Window", tick=None):
    throw = tick if tick is not None else 1000 * round_number
    return Grenade(
        kind=kind,
        round_number=round_number,
        thrower=player,
        side=TeamSide.TERRORIST,
        throw_tick=throw,
        detonate_tick=throw + 320,
        thrower_position=Vector3(0.0, 0.0, 0.0),
        thrower_angles=ViewAngles(-10.0, 45.0),
        landing=Vector3(100.0, 0.0, 0.0),
        landing_place=place,
    )


@pytest.fixture
def roster():
    return make_player(1, "s1mple"), make_player(2, "-n1clxe")


@pytest.fixture
def highlights(roster):
    first, second = roster
    return [
        make_highlight(1, first, (AWP,), weapon="awp"),
        make_highlight(4, second, (CLUTCH,), kills=3),
        make_highlight(7, first, (AWP, CLUTCH), weapon="awp"),
    ]


def select(highlights, **criteria):
    return HighlightSelection(SelectionCriteria.from_mapping(criteria)).apply(highlights)


def test_no_criteria_keeps_everything(highlights):
    assert len(select(highlights)) == len(highlights)


def test_rounds_narrow_the_result(highlights):
    picked = select(highlights, rounds=[1, 7])

    assert [item.round_number for item in picked] == [1, 7]


def test_a_round_range_narrows_the_result(highlights):
    picked = select(highlights, roundRange={"from": 4, "to": 9})

    assert [item.round_number for item in picked] == [4, 7]


def test_a_player_name_narrows_the_result(highlights, roster):
    picked = select(highlights, players=["s1mple"])

    assert {item.player.name for item in picked} == {"s1mple"}


def test_a_steam_id_narrows_the_result(highlights, roster):
    first, _ = roster
    picked = select(highlights, players=[str(first.steam_id64)])

    assert {item.player.steam_id64 for item in picked} == {first.steam_id64}


def test_a_name_starting_with_a_dash_is_a_plain_query(highlights):
    assert len(select(highlights, players=["-n1clxe"])) == 1


def test_a_partial_name_still_matches(highlights):
    assert len(select(highlights, players=["s1mp"])) == 2


def test_rounds_and_players_narrow_together(highlights, roster):
    picked = select(highlights, rounds=[1, 4, 7], players=["s1mple"])

    assert [item.round_number for item in picked] == [1, 7]


def test_identifiers_pick_exactly_those_items(highlights):
    wanted = Identity.for_highlight(highlights[1])
    picked = select(highlights, ids=[wanted])

    assert [Identity.for_highlight(item) for item in picked] == [wanted]


def test_identifiers_are_stable_across_calls(highlights):
    assert Identity.for_highlight(highlights[0]) == Identity.for_highlight(highlights[0])


def test_tags_narrow_the_result(highlights):
    picked = select(highlights, tags=["clutch_1v3"])

    assert [item.round_number for item in picked] == [4, 7]


def test_weapons_narrow_the_result(highlights):
    picked = select(highlights, weapons=["awp"])

    assert [item.round_number for item in picked] == [1, 7]


def test_a_minimum_score_narrows_the_result(highlights):
    assert [item.round_number for item in select(highlights, minimumScore=20)] == [4, 7]


def test_a_minimum_kill_count_narrows_the_result(highlights):
    assert [item.round_number for item in select(highlights, minimumKills=3)] == [4]


def test_score_order_puts_the_best_first(highlights):
    picked = select(highlights, order="score_desc")

    assert picked[0].score >= picked[-1].score


def test_round_order_is_the_default(highlights):
    assert [item.round_number for item in select(highlights)] == [1, 4, 7]


def test_a_limit_cuts_the_tail(highlights):
    assert len(select(highlights, limit=2)) == 2


def test_an_unknown_order_is_rejected():
    with pytest.raises(BadRequestError):
        SelectionCriteria.from_mapping({"order": "sideways"})


def test_a_selection_that_is_not_an_object_is_rejected():
    with pytest.raises(BadRequestError):
        SelectionCriteria.from_mapping(["round", 1])


def test_a_backwards_round_range_is_rejected():
    with pytest.raises(BadRequestError):
        SelectionCriteria.from_mapping({"roundRange": {"from": 9, "to": 2}})


def test_a_round_that_is_not_a_number_is_rejected():
    with pytest.raises(BadRequestError):
        SelectionCriteria.from_mapping({"rounds": ["banana"]})


def test_an_empty_selection_reports_itself_as_empty():
    assert SelectionCriteria.from_mapping({}).is_empty is True
    assert SelectionCriteria.from_mapping({"rounds": [1]}).is_empty is False


@pytest.fixture
def grenades(roster):
    first, second = roster
    return [
        make_grenade(1, first, GrenadeKind.SMOKE, "Window"),
        make_grenade(3, second, GrenadeKind.FLASH, "Connector"),
        make_grenade(5, first, GrenadeKind.SMOKE, "BombsiteB"),
    ]


def pick(grenades, **criteria):
    return GrenadeSelection(SelectionCriteria.from_mapping(criteria)).apply(grenades)


def test_grenade_kinds_narrow_the_result(grenades):
    picked = pick(grenades, grenadeKinds=["smoke"])

    assert {item.kind for item in picked} == {GrenadeKind.SMOKE}


def test_a_grenade_alias_is_understood(grenades):
    assert len(pick(grenades, grenadeKinds=["flashbang"])) == 1


def test_an_unknown_grenade_kind_is_rejected():
    with pytest.raises(BadRequestError):
        SelectionCriteria.from_mapping({"grenadeKinds": ["banana"]})


def test_a_landing_place_narrows_the_result(grenades):
    picked = pick(grenades, landingPlaces=["window"])

    assert [item.landing_place for item in picked] == ["Window"]


def test_a_landing_place_matches_without_exact_case(grenades):
    assert len(pick(grenades, landingPlaces=["BOMBSITEB"])) == 1


def test_grenade_rounds_and_players_narrow_together(grenades, roster):
    first, _ = roster
    picked = pick(grenades, rounds=[1, 5], players=[str(first.steam_id64)])

    assert [item.round_number for item in picked] == [1, 5]


def test_grenade_identifiers_pick_exactly_those_items(grenades):
    wanted = Identity.for_grenade(grenades[2])

    assert [Identity.for_grenade(item) for item in pick(grenades, ids=[wanted])] == [wanted]


def test_grenade_identifiers_separate_two_throws_in_one_round(roster):
    first, _ = roster
    early = make_grenade(2, first, tick=500)
    late = make_grenade(2, first, tick=900)

    assert Identity.for_grenade(early) != Identity.for_grenade(late)


def test_grenades_come_back_in_throw_order(grenades):
    picked = pick(grenades)

    assert [item.throw_tick for item in picked] == sorted(item.throw_tick for item in picked)


def test_a_grenade_limit_cuts_the_tail(grenades):
    assert len(pick(grenades, limit=1)) == 1
