from __future__ import annotations

from conftest import make_kill, make_roster, make_round

from highlighter.config.schema import DetectionConfig
from highlighter.detection.engine import HighlightEngine
from highlighter.domain.team import TeamSide


def detect(match, **overrides):
    settings = DetectionConfig(**{"minimum_score": 1.0, **overrides})
    return HighlightEngine(settings).detect(match)


def test_ace_outscores_a_double_kill(match, terrorists, counter_terrorists):
    roster = make_roster(terrorists, counter_terrorists)
    ace_round = make_round(
        number=1,
        roster=roster,
        kills=[
            make_kill(1100 + offset * 100, terrorists[0], victim)
            for offset, victim in enumerate(counter_terrorists)
        ],
    )
    double_round = make_round(
        number=2,
        roster=roster,
        freeze_end_tick=9000,
        end_tick=16000,
        kills=[
            make_kill(9100, terrorists[1], counter_terrorists[0], round_number=2),
            make_kill(9200, terrorists[1], counter_terrorists[1], round_number=2),
        ],
    )
    match.rounds.extend([ace_round, double_round])

    highlights = detect(match)

    assert highlights[0].kill_count == 5
    assert "kills_5" in highlights[0].tag_codes
    assert highlights[0].score > highlights[1].score


def test_awp_double_kill_is_tagged(match, terrorists, counter_terrorists):
    match.rounds.append(
        make_round(
            roster=make_roster(terrorists, counter_terrorists),
            kills=[
                make_kill(1100, terrorists[0], counter_terrorists[0], weapon="awp"),
                make_kill(1300, terrorists[0], counter_terrorists[1], weapon="awp"),
            ],
        )
    )

    highlights = detect(match)

    assert len(highlights) == 1
    assert "awp_double" in highlights[0].tag_codes


def test_team_kills_are_ignored(match, terrorists, counter_terrorists):
    match.rounds.append(
        make_round(
            roster=make_roster(terrorists, counter_terrorists),
            kills=[
                make_kill(
                    1100,
                    terrorists[0],
                    terrorists[1],
                    victim_side=TeamSide.TERRORIST,
                ),
                make_kill(
                    1200,
                    terrorists[0],
                    terrorists[2],
                    victim_side=TeamSide.TERRORIST,
                ),
            ],
        )
    )

    assert detect(match) == []


def test_minimum_score_filters_weak_rounds(match, terrorists, counter_terrorists):
    match.rounds.append(
        make_round(
            roster=make_roster(terrorists, counter_terrorists),
            kills=[
                make_kill(1100, terrorists[0], counter_terrorists[0]),
                make_kill(1200, terrorists[0], counter_terrorists[1]),
            ],
        )
    )

    assert detect(match, minimum_score=1000.0) == []


def test_maximum_highlights_limits_output(match, terrorists, counter_terrorists):
    roster = make_roster(terrorists, counter_terrorists)
    for number in range(1, 6):
        match.rounds.append(
            make_round(
                number=number,
                roster=roster,
                freeze_end_tick=number * 10000,
                end_tick=number * 10000 + 8000,
                kills=[
                    make_kill(number * 10000 + 100, terrorists[0], counter_terrorists[0],
                              round_number=number),
                    make_kill(number * 10000 + 200, terrorists[0], counter_terrorists[1],
                              round_number=number),
                ],
            )
        )

    assert len(detect(match, maximum_highlights=2)) == 2


def test_second_half_pistol_round_is_detected(match, terrorists, counter_terrorists):
    first_half = make_roster(terrorists, counter_terrorists)
    second_half = make_roster(counter_terrorists, terrorists)

    match.rounds.append(
        make_round(
            number=1,
            roster=first_half,
            kills=[
                make_kill(1100, terrorists[0], counter_terrorists[0], weapon="glock"),
                make_kill(1200, terrorists[0], counter_terrorists[1], weapon="glock"),
            ],
        )
    )
    match.rounds.append(
        make_round(
            number=13,
            roster=second_half,
            freeze_end_tick=90000,
            end_tick=96000,
            kills=[
                make_kill(90100, terrorists[0], counter_terrorists[0], weapon="glock",
                          attacker_side=TeamSide.COUNTER_TERRORIST,
                          victim_side=TeamSide.TERRORIST, round_number=13),
                make_kill(90200, terrorists[0], counter_terrorists[1], weapon="glock",
                          attacker_side=TeamSide.COUNTER_TERRORIST,
                          victim_side=TeamSide.TERRORIST, round_number=13),
            ],
        )
    )

    highlights = detect(match)
    pistol_rounds = {
        highlight.round_number
        for highlight in highlights
        if "pistol_round" in highlight.tag_codes
    }

    assert pistol_rounds == {1, 13}
