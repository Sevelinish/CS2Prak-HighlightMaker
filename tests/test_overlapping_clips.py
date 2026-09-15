from __future__ import annotations

from pathlib import Path

import pytest
from conftest import make_kill, make_player, make_round, make_roster

from highlighter.config.schema import GameConfig, NadeConfig, RecordingConfig
from highlighter.domain.geometry import Vector3, ViewAngles
from highlighter.domain.grenade import Grenade, GrenadeKind
from highlighter.domain.highlight import Highlight, HighlightTag
from highlighter.domain.match import Match
from highlighter.domain.player import Player
from highlighter.domain.round import Round
from highlighter.domain.team import TeamSide
from highlighter.media.encoders import EncoderProfile
from highlighter.plan.builder import RecordingPlanBuilder
from highlighter.plan.grouping import OverlapGrouper, Window
from highlighter.plan.models import RecordingPlan
from highlighter.plan.nade_builder import NadePlanBuilder
from highlighter.recording.mirv_script import MirvScriptBuilder

ENCODER = EncoderProfile("libx264", ("-c:v", "libx264"), "mp4", False)
TICK_RATE = 64
THROWER = Player(76561198000000000, "kul", 5)


@pytest.fixture
def nade_match() -> Match:
    match = Match(demo_path=Path("m.dem"), map_name="de_mirage", tick_rate=TICK_RATE)
    match.rounds.append(
        Round(number=3, freeze_end_tick=0, end_tick=60_000, winner=None, end_reason=None)
    )
    return match


def smoke(throw: int, detonate: int, x: float, place: str = "Window") -> Grenade:
    return Grenade(
        kind=GrenadeKind.SMOKE,
        round_number=3,
        thrower=THROWER,
        side=None,
        throw_tick=throw,
        detonate_tick=detonate,
        thrower_position=Vector3(0.0, 0.0, 0.0),
        thrower_angles=ViewAngles(0.0, 0.0),
        landing=Vector3(x, 0.0, 0.0),
        landing_place=place,
    )


def build_nades(match: Match, grenades: list[Grenade]) -> RecordingPlan:
    return NadePlanBuilder(RecordingConfig(), NadeConfig()).build(
        match, grenades, Path("out")
    )


def scheduled(plan: RecordingPlan) -> list[tuple[int, str]]:
    bundle = MirvScriptBuilder(
        RecordingConfig(), ENCODER, GameConfig(), Path("takes")
    ).build(plan)
    session = next(
        item.content for item in bundle.files if item.name == "highlighter_session"
    )
    rows = [
        (int(line.split()[2]), line.split()[4])
        for line in session.splitlines()
        if line.startswith("mirv_cmd addAtTick")
    ]
    return sorted(rows)


def segment_windows(plan: RecordingPlan) -> list[tuple[int, int]]:
    return sorted(
        (segment.start_tick, segment.end_tick)
        for clip in plan.clips
        for segment in clip.segments
    )


def test_two_throws_a_second_apart_become_one_clip(nade_match):
    plan = build_nades(nade_match, [smoke(10_000, 10_640, 500), smoke(10_064, 10_704, 900)])

    assert plan.clip_count == 1
    assert plan.merged_sources == 1


def test_two_throws_far_apart_stay_separate(nade_match):
    plan = build_nades(nade_match, [smoke(10_000, 10_640, 500), smoke(20_000, 20_640, 900)])

    assert plan.clip_count == 2
    assert plan.merged_sources == 0


def test_a_merged_clip_covers_both_throws(nade_match):
    plan = build_nades(nade_match, [smoke(10_000, 10_640, 500), smoke(10_064, 10_704, 900)])
    clip = plan.clips[0]

    assert clip.action_start_tick == 10_000
    assert clip.action_end_tick == 10_704
    assert set(clip.segments[0].kill_ticks) == {10_000, 10_064}


def test_a_merged_clip_zooms_only_once(nade_match):
    plan = build_nades(nade_match, [smoke(10_000, 10_640, 500), smoke(10_064, 10_704, 900)])
    names = [beat.name for beat in plan.clips[0].beats]

    assert names.count("zoom") == 1
    assert names.count("unzoom") == 1


def test_the_zoom_hold_sits_before_the_first_throw(nade_match):
    plan = build_nades(nade_match, [smoke(10_000, 10_640, 500), smoke(10_064, 10_704, 900)])
    zoom = next(beat for beat in plan.clips[0].beats if beat.name == "zoom")

    assert zoom.tick < 10_000


def test_the_recording_schedule_never_interleaves(nade_match):
    plan = build_nades(nade_match, [smoke(10_000, 10_640, 500), smoke(10_064, 10_704, 900)])
    recording = False

    for _, script in scheduled(plan):
        if script.endswith("_start"):
            assert recording is False
            recording = True
        elif script.endswith("_end"):
            assert recording is True
            recording = False

    assert recording is False


def test_no_two_segments_overlap_in_a_grenade_plan(nade_match):
    plan = build_nades(
        nade_match,
        [
            smoke(10_000, 10_640, 500),
            smoke(10_064, 10_704, 900),
            smoke(10_200, 10_900, 300),
            smoke(30_000, 30_640, 100),
        ],
    )
    windows = segment_windows(plan)

    assert all(
        earlier[1] <= later[0] for earlier, later in zip(windows, windows[1:])
    )


def test_three_throws_in_a_burst_become_one_clip(nade_match):
    plan = build_nades(
        nade_match,
        [smoke(10_000, 10_640, 500), smoke(10_064, 10_704, 900), smoke(10_128, 10_800, 300)],
    )

    assert plan.clip_count == 1
    assert plan.merged_sources == 2


def test_a_chain_of_throws_does_not_swallow_a_distant_one(nade_match):
    plan = build_nades(
        nade_match,
        [smoke(10_000, 10_640, 500), smoke(10_064, 10_704, 900), smoke(40_000, 40_640, 300)],
    )

    assert plan.clip_count == 2
    assert plan.merged_sources == 1


def test_the_merged_clip_is_named_after_the_burst(nade_match):
    plan = build_nades(
        nade_match,
        [smoke(10_000, 10_640, 500, "Window"), smoke(10_064, 10_704, 900, "Palace")],
    )

    assert "2xsmoke" in plan.clips[0].name
    assert "window" in plan.clips[0].name


def test_the_note_says_the_throws_were_filmed_together(nade_match):
    plan = build_nades(nade_match, [smoke(10_000, 10_640, 500), smoke(10_064, 10_704, 900)])

    assert "2 throws filmed as one clip" in plan.clips[0].note


def test_the_camera_pulls_back_to_hold_both_landings(nade_match):
    plan = build_nades(nade_match, [smoke(10_000, 10_640, 500), smoke(10_064, 10_704, 900)])
    landing = plan.clips[0].segments[-1].setup_commands or next(
        beat.commands for beat in plan.clips[0].beats if beat.name == "landing"
    )
    coordinates = [float(value) for value in landing[1].split()[1:4]]
    centre = Vector3(700.0, 0.0, 0.0)
    camera = Vector3(*coordinates)

    assert camera.distance_to(centre) > NadeConfig().landing_distance
    assert camera.distance_to(Vector3(500.0, 0.0, 0.0)) > 0
    assert camera.distance_to(Vector3(900.0, 0.0, 0.0)) > 0


def test_the_group_camera_is_reported_in_the_note(nade_match):
    plan = build_nades(nade_match, [smoke(10_000, 10_640, 500), smoke(10_064, 10_704, 900)])

    assert "landing camera group" in plan.clips[0].note


def test_a_single_throw_keeps_its_own_camera(nade_match):
    plan = build_nades(nade_match, [smoke(10_000, 10_640, 500)])

    assert "landing camera group" not in plan.clips[0].note
    assert plan.merged_sources == 0


@pytest.fixture
def highlight_match() -> tuple[Match, list, list]:
    terrorists = [make_player(1, "ally"), make_player(2, "mate")]
    counters = [make_player(11, "foe1"), make_player(12, "foe2")]
    match = Match(demo_path=Path("m.dem"), map_name="de_mirage", tick_rate=TICK_RATE)
    return match, terrorists, counters


def test_two_players_in_the_same_firefight_become_one_clip(highlight_match):
    match, terrorists, counters = highlight_match
    kills = [
        make_kill(5_000, terrorists[0], counters[0]),
        make_kill(5_200, terrorists[0], counters[1]),
        make_kill(5_100, terrorists[1], counters[0]),
        make_kill(5_300, terrorists[1], counters[1]),
    ]
    match.rounds.append(
        make_round(number=1, roster=make_roster(terrorists, counters), kills=kills)
    )
    tag = (HighlightTag("kills_2", "2K", 4.0),)
    highlights = [
        Highlight(1, terrorists[0], TeamSide.TERRORIST, (kills[0], kills[1]), tag),
        Highlight(1, terrorists[1], TeamSide.TERRORIST, (kills[2], kills[3]), tag),
    ]

    plan = RecordingPlanBuilder(RecordingConfig()).build(match, highlights, Path("out"))
    windows = segment_windows(plan)

    assert plan.clip_count == 1
    assert plan.merged_sources == 1
    assert all(earlier[1] <= later[0] for earlier, later in zip(windows, windows[1:]))
    assert "share this stretch" in plan.clips[0].note


def test_highlights_in_different_rounds_stay_separate(highlight_match):
    match, terrorists, counters = highlight_match
    first = make_kill(5_000, terrorists[0], counters[0], round_number=1)
    second = make_kill(40_000, terrorists[1], counters[1], round_number=2)
    match.rounds.append(
        make_round(number=1, roster=make_roster(terrorists, counters), kills=[first])
    )
    match.rounds.append(
        make_round(
            number=2,
            roster=make_roster(terrorists, counters),
            kills=[second],
            freeze_end_tick=39_000,
            end_tick=48_000,
        )
    )
    tag = (HighlightTag("kills_2", "2K", 4.0),)
    highlights = [
        Highlight(1, terrorists[0], TeamSide.TERRORIST, (first,), tag),
        Highlight(2, terrorists[1], TeamSide.TERRORIST, (second,), tag),
    ]

    plan = RecordingPlanBuilder(RecordingConfig()).build(match, highlights, Path("out"))

    assert plan.clip_count == 2
    assert plan.merged_sources == 0


def test_windows_that_only_touch_are_grouped():
    groups = OverlapGrouper.group(
        [Window(0, 100), Window(100, 200), Window(400, 500)], lambda item: item
    )

    assert [len(group) for group in groups] == [2, 1]


def test_windows_that_are_apart_are_not_grouped():
    groups = OverlapGrouper.group(
        [Window(0, 100), Window(101, 200)], lambda item: item
    )

    assert [len(group) for group in groups] == [1, 1]


def test_grouping_counts_how_many_were_folded_in():
    groups = OverlapGrouper.group(
        [Window(0, 100), Window(50, 150), Window(120, 200), Window(900, 950)],
        lambda item: item,
    )

    assert OverlapGrouper.merged_count(groups) == 2


def test_landings_too_far_apart_fall_back_to_the_first_throw(nade_match):
    plan = build_nades(
        nade_match, [smoke(10_000, 10_640, 0), smoke(10_064, 10_704, 4_000, "Palace")]
    )

    assert plan.clip_count == 1
    assert "landing camera group" not in plan.clips[0].note


def test_a_clip_never_starts_after_its_own_action(nade_match):
    late_round = Match(demo_path=Path("m.dem"), map_name="de_mirage", tick_rate=TICK_RATE)
    late_round.rounds.append(
        Round(number=3, freeze_end_tick=20_000, end_tick=60_000, winner=None, end_reason=None)
    )
    plan = build_nades(late_round, [smoke(10_000, 10_640, 500)])
    clip = plan.clips[0]

    assert clip.start_tick < 10_000
    assert clip.end_tick > 10_640


def test_a_clip_never_ends_before_its_own_action(nade_match):
    early_end = Match(demo_path=Path("m.dem"), map_name="de_mirage", tick_rate=TICK_RATE)
    early_end.rounds.append(
        Round(number=3, freeze_end_tick=0, end_tick=5_000, winner=None, end_reason=None)
    )
    plan = build_nades(early_end, [smoke(10_000, 10_640, 500)])
    segment = plan.clips[0].segments[-1]

    assert segment.end_tick > 10_640


def test_a_kill_before_the_round_freeze_end_still_gets_its_lead_in():
    from highlighter.plan.segmenter import ClipSegmenter

    match = Match(demo_path=Path("m.dem"), map_name="de_mirage", tick_rate=TICK_RATE)
    attacker = make_player(1, "ally")
    victim = make_player(11, "foe")
    kill = make_kill(3_000, attacker, victim)
    round_ = make_round(number=2, freeze_end_tick=9_000, end_tick=20_000, kills=[kill])

    segments = ClipSegmenter(RecordingConfig(), match).segment((kill,), round_)

    assert segments[0].start_tick < 3_000
