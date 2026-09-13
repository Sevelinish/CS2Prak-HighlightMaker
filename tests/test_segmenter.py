from __future__ import annotations

import pytest
from conftest import TICK_RATE, make_kill, make_player, make_round

from highlighter.config.schema import RecordingConfig
from highlighter.plan.segmenter import ClipSegmenter

SETTINGS = RecordingConfig(
    lead_in_seconds=2.0,
    resume_lead_seconds=1.5,
    gap_hold_seconds=4.0,
    post_roll_seconds=2.5,
)
ROOMY_ROUND = make_round(freeze_end_tick=0, end_tick=1_000_000)


def seconds(value: float) -> int:
    return int(round(value * TICK_RATE))


def build_kills(offsets_in_seconds: list[float], base_tick: int = 10_000):
    attacker = make_player(1)
    victim = make_player(11)
    return tuple(
        make_kill(base_tick + seconds(offset), attacker, victim)
        for offset in offsets_in_seconds
    )


def segment(match, offsets: list[float], settings: RecordingConfig = SETTINGS):
    return ClipSegmenter(settings, match).segment(build_kills(offsets), ROOMY_ROUND)


def test_single_kill_gets_lead_in_and_post_roll(match):
    segments = segment(match, [0.0])

    assert len(segments) == 1
    assert segments[0].start_tick == 10_000 - seconds(2.0)
    assert segments[0].end_tick == 10_000 + seconds(2.5)


def test_kills_inside_the_hold_window_stay_in_one_segment(match):
    segments = segment(match, [0.0, 3.0, 6.0])

    assert len(segments) == 1
    assert segments[0].kill_ticks == (10_000, 10_000 + seconds(3.0), 10_000 + seconds(6.0))


def test_a_long_gap_starts_a_new_segment(match):
    segments = segment(match, [0.0, 20.0])

    assert len(segments) == 2
    assert segments[0].end_tick == 10_000 + seconds(4.0)
    assert segments[1].start_tick == 10_000 + seconds(20.0) - seconds(1.5)


def test_new_segment_uses_the_shorter_resume_lead(match):
    segments = segment(match, [0.0, 30.0])

    first_lead = segments[0].kill_ticks[0] - segments[0].start_tick
    second_lead = segments[1].kill_ticks[0] - segments[1].start_tick

    assert first_lead == seconds(2.0)
    assert second_lead == seconds(1.5)


CUT_THRESHOLD_SECONDS = (
    SETTINGS.gap_hold_seconds
    + SETTINGS.resume_lead_seconds
    + SETTINGS.seek_lead_ticks / TICK_RATE
)


def test_gap_shorter_than_the_skip_cost_is_not_cut(match):
    segments = segment(match, [0.0, CUT_THRESHOLD_SECONDS - 0.5])

    assert len(segments) == 1


def test_gap_just_past_the_threshold_is_cut(match):
    segments = segment(match, [0.0, CUT_THRESHOLD_SECONDS + 0.5])

    assert len(segments) == 2


def test_a_gap_that_cannot_seek_forward_is_never_cut(match):
    for gap in (5.6, 6.0, 6.5, 7.0, 7.4):
        assert len(segment(match, [0.0, gap])) == 1, f"gap {gap}s would seek backwards"


def test_only_the_final_segment_uses_post_roll(match):
    segments = segment(match, [0.0, 20.0, 40.0])

    assert len(segments) == 3
    assert segments[0].end_tick - segments[0].kill_ticks[-1] == seconds(4.0)
    assert segments[1].end_tick - segments[1].kill_ticks[-1] == seconds(4.0)
    assert segments[2].end_tick - segments[2].kill_ticks[-1] == seconds(2.5)


def test_segmentation_removes_dead_time(match):
    segments = segment(match, [0.0, 60.0])

    covered = segments[-1].end_tick - segments[0].start_tick
    recorded = sum(item.end_tick - item.start_tick for item in segments)

    assert recorded < covered / 2


def test_segments_are_ordered_and_disjoint(match):
    segments = segment(match, [0.0, 20.0, 45.0, 48.0])

    for earlier, later in zip(segments, segments[1:]):
        assert earlier.end_tick <= later.start_tick


def test_segment_indexes_start_at_one(match):
    segments = segment(match, [0.0, 20.0, 40.0])

    assert [item.index for item in segments] == [1, 2, 3]
    assert [item.name for item in segments] == ["s01", "s02", "s03"]


def test_segments_stay_inside_the_round(match):
    kills = build_kills([0.0, 20.0])
    tight_round = make_round(freeze_end_tick=9_950, end_tick=11_500)

    segments = ClipSegmenter(SETTINGS, match).segment(kills, tight_round)

    assert segments[0].start_tick >= 9_950
    assert all(item.end_tick <= 11_500 for item in segments)


def test_no_kills_produces_no_segments(match):
    assert ClipSegmenter(SETTINGS, match).segment((), ROOMY_ROUND) == ()


@pytest.mark.parametrize("hold", [1.0, 4.0, 10.0])
def test_hold_window_controls_how_eagerly_clips_are_cut(match, hold: float):
    settings = RecordingConfig(
        lead_in_seconds=2.0,
        resume_lead_seconds=1.5,
        gap_hold_seconds=hold,
        post_roll_seconds=2.5,
    )
    threshold = hold + 1.5 + settings.seek_lead_ticks / TICK_RATE
    segments = segment(match, [0.0, 8.0], settings)

    assert len(segments) == (1 if threshold >= 8.0 else 2)


def test_slot_travels_from_the_demo_into_the_plan(match):
    from highlighter.domain.player import Player

    player = Player(steam_id64=76561198717658391, name="kulbergenn12", slot=5)

    assert player.has_slot
    assert player.slot == 5
    assert Player(steam_id64=1, name="x").has_slot is False
