from __future__ import annotations

import re
from pathlib import Path

import pytest
from conftest import make_kill, make_player, make_round, make_roster

from highlighter.config.schema import GameConfig, RecordingConfig
from highlighter.domain.highlight import Highlight, HighlightTag
from highlighter.domain.match import Match
from highlighter.domain.team import TeamSide
from highlighter.media.encoders import EncoderProfile
from highlighter.plan.builder import RecordingPlanBuilder
from highlighter.plan.models import RecordingPlan
from highlighter.plan.passes import PassPlanner, PassSlot
from highlighter.recording.mirv_script import MirvScriptBuilder

ENCODER = EncoderProfile("libx264", ("-c:v", "libx264"), "mp4", False)
TICK_RATE = 64
TAG = (HighlightTag("kills_3", "3K", 12.0),)


def match_with(kill_ticks: list[int]) -> tuple[Match, Highlight]:
    match = Match(demo_path=Path("m.dem"), map_name="de_mirage", tick_rate=TICK_RATE)
    attacker = make_player(1, "ally").with_slot(1)
    victims = [
        make_player(11 + index, f"foe{index}").with_slot(index + 2)
        for index in range(len(kill_ticks))
    ]
    for victim in victims:
        match.players[victim.steam_id64] = victim
    match.players[attacker.steam_id64] = attacker

    kills = [
        make_kill(tick, attacker, victims[index]) for index, tick in enumerate(kill_ticks)
    ]
    match.rounds.append(
        make_round(
            number=1,
            roster=make_roster([attacker], victims),
            kills=kills,
            freeze_end_tick=1_000,
            end_tick=60_000,
        )
    )
    return match, Highlight(1, attacker, TeamSide.TERRORIST, tuple(kills), TAG)


def build(kill_ticks: list[int], enemy: bool = True) -> RecordingPlan:
    match, highlight = match_with(kill_ticks)
    settings = RecordingConfig(record_enemy_view=enemy)
    return RecordingPlanBuilder(settings).build(match, [highlight], Path("out"))


def scripts(plan: RecordingPlan, settings: RecordingConfig):
    return MirvScriptBuilder(
        settings, ENCODER, GameConfig(), Path("takes"), Path("C:/cfg")
    ).build(plan)


def test_without_the_flag_nothing_changes():
    clip = build([5_000, 5_400, 5_800], enemy=False).clips[0]

    assert all(segment.label == "" for segment in clip.segments)
    assert all(segment.pass_index == 1 for segment in clip.segments)


def test_every_kill_gets_a_segment_from_the_victim():
    clip = build([5_000, 5_400, 5_800]).clips[0]
    enemies = [segment for segment in clip.segments if segment.label == "enemy"]

    assert len(enemies) == 3


def test_the_player_view_comes_first_in_the_file():
    segments = build([5_000, 5_400, 5_800]).clips[0].segments
    labels = [segment.label for segment in segments]

    assert labels.index("enemy") == labels.count("")
    assert labels[-1] == "enemy"


def test_the_victim_segments_follow_the_order_of_the_kills():
    segments = build([5_000, 5_400, 5_800]).clips[0].segments
    enemies = [segment for segment in segments if segment.label == "enemy"]

    assert [segment.kill_ticks[0] for segment in enemies] == [5_000, 5_400, 5_800]


def test_a_victim_segment_spectates_the_victim():
    enemies = [s for s in build([5_000]).clips[0].segments if s.label == "enemy"]

    assert enemies[0].player is not None
    assert enemies[0].player.name == "foe0"


def test_a_victim_segment_carries_the_spectator_slot():
    enemies = [s for s in build([5_000]).clips[0].segments if s.label == "enemy"]

    assert enemies[0].player.slot == 2


def test_a_victim_segment_frames_its_own_kill():
    settings = RecordingConfig()
    enemies = [s for s in build([5_000]).clips[0].segments if s.label == "enemy"]
    segment = enemies[0]

    assert segment.start_tick == 5_000 - int(settings.enemy_lead_seconds * TICK_RATE)
    assert segment.end_tick == 5_000 + int(settings.enemy_hold_seconds * TICK_RATE)


def test_the_player_view_always_records_in_the_first_pass():
    clip = build([5_000, 5_400, 5_800]).clips[0]

    assert all(s.pass_index == 1 for s in clip.segments if s.label != "enemy")


def test_a_victim_never_shares_a_pass_with_the_player_view():
    clip = build([5_000, 5_400, 5_800]).clips[0]

    assert all(s.pass_index > 1 for s in clip.segments if s.label == "enemy")


def test_victims_far_apart_share_one_pass():
    clip = build([5_000, 9_000, 13_000]).clips[0]
    enemies = [s.pass_index for s in clip.segments if s.label == "enemy"]

    assert enemies == [2, 2, 2]


def test_victims_close_together_take_separate_passes():
    clip = build([5_000, 5_100, 5_200]).clips[0]
    enemies = [s.pass_index for s in clip.segments if s.label == "enemy"]

    assert len(set(enemies)) == len(enemies)


def test_no_two_segments_in_a_pass_overlap():
    plan = build([5_000, 5_100, 5_200, 9_000])
    by_pass: dict[int, list[tuple[int, int]]] = {}
    for clip in plan.clips:
        for segment in clip.segments:
            by_pass.setdefault(segment.pass_index, []).append(
                (segment.start_tick, segment.end_tick)
            )

    for windows in by_pass.values():
        windows.sort()
        assert all(a[1] <= b[0] for a, b in zip(windows, windows[1:]))


def test_the_session_script_schedules_only_the_first_pass():
    settings = RecordingConfig(record_enemy_view=True)
    plan = build([5_000, 5_100, 5_200])
    session = next(
        f.content for f in scripts(plan, settings).files if f.name == "highlighter_session"
    )
    scheduled = set(re.findall(r"addAtTick \d+ exec (\S+_start)", session))
    wanted = {
        f"highlighter_c{clip.index:02d}_{segment.name}_start"
        for clip in plan.clips
        for segment in clip.segments
        if segment.pass_index == 1
    }

    assert scheduled == wanted


def test_a_later_pass_gets_its_own_script():
    settings = RecordingConfig(record_enemy_view=True)
    bundle = scripts(build([5_000, 5_100, 5_200]), settings)
    names = {f.name for f in bundle.files}

    assert "highlighter_pass02" in names
    assert "highlighter_pass03" in names


def test_a_pass_script_clears_before_it_schedules():
    settings = RecordingConfig(record_enemy_view=True)
    bundle = scripts(build([5_000, 5_100]), settings)
    content = next(f.content for f in bundle.files if f.name == "highlighter_pass02")

    assert content.splitlines()[0] == "mirv_cmd clear"


def test_a_pass_script_rewinds_before_its_own_first_entry():
    settings = RecordingConfig(record_enemy_view=True)
    plan = build([5_000, 5_100])
    content = next(
        f.content for f in scripts(plan, settings).files if f.name == "highlighter_pass02"
    )
    rewind = int(re.search(r"demo_gototick (\d+)", content).group(1))
    starts = [
        segment.start_tick
        for clip in plan.clips
        for segment in clip.segments
        if segment.pass_index == 2
    ]

    assert rewind < min(starts)


def test_a_pass_script_rewinds_after_it_schedules():
    settings = RecordingConfig(record_enemy_view=True)
    bundle = scripts(build([5_000, 5_100]), settings)
    lines = next(
        f.content for f in bundle.files if f.name == "highlighter_pass02"
    ).splitlines()

    assert lines[-1].startswith("demo_gototick ")
    assert any(line.startswith("mirv_cmd addAtTick") for line in lines[:-1])


def test_the_last_take_of_a_pass_hands_over_to_the_next():
    settings = RecordingConfig(record_enemy_view=True)
    plan = build([5_000, 5_100])
    bundle = scripts(plan, settings)
    handoffs = [
        f.name for f in bundle.files if f.name.endswith("_end") and "exec highlighter_pass" in f.content
    ]
    passes = {segment.pass_index for clip in plan.clips for segment in clip.segments}

    assert len(handoffs) == len(passes) - 1


def test_the_very_last_take_still_closes_the_game():
    settings = RecordingConfig(record_enemy_view=True)
    bundle = scripts(build([5_000, 5_100]), settings)
    quitting = [f for f in bundle.files if " quit" in f.content]

    assert len(quitting) == 1
    assert "exec highlighter_pass" not in quitting[0].content


def test_a_victim_take_aims_the_camera_at_the_victim():
    settings = RecordingConfig(record_enemy_view=True)
    plan = build([5_000])
    enemy = next(s for s in plan.clips[0].segments if s.label == "enemy")
    start = next(
        f.content
        for f in scripts(plan, settings).files
        if f.name == f"highlighter_c01_{enemy.name}_start"
    )

    assert "spec_player 2" in start
    assert str(enemy.player.account_id) in start


def test_a_player_take_still_aims_at_the_player():
    settings = RecordingConfig(record_enemy_view=True)
    plan = build([5_000])
    start = next(
        f.content for f in scripts(plan, settings).files if f.name == "highlighter_c01_s01_start"
    )

    assert "spec_player 1" in start


def test_nothing_is_scheduled_twice_across_passes():
    settings = RecordingConfig(record_enemy_view=True)
    plan = build([5_000, 5_100, 5_200])
    bundle = scripts(plan, settings)
    every = []
    for item in bundle.files:
        if item.name == "highlighter_session" or item.name.startswith("highlighter_pass"):
            every += re.findall(r"addAtTick \d+ exec (\S+_start)", item.content)

    assert len(every) == len(set(every))
    assert len(every) == sum(len(clip.segments) for clip in plan.clips)


def test_slots_are_packed_into_as_few_passes_as_possible():
    planner = PassPlanner()
    numbers = planner.assign(
        [PassSlot(0, 100), PassSlot(50, 150), PassSlot(200, 300), PassSlot(250, 350)]
    )

    assert numbers == [1, 2, 1, 2]


def test_reserved_slots_always_land_in_the_first_pass():
    planner = PassPlanner()
    numbers = planner.assign(
        [PassSlot(500, 900), PassSlot(0, 100), PassSlot(520, 560)], reserved=1
    )

    assert numbers[0] == 1
    assert numbers[2] > 1


def test_a_margin_keeps_passes_from_touching():
    planner = PassPlanner(margin_ticks=200)
    numbers = planner.assign([PassSlot(0, 100), PassSlot(150, 250)])

    assert numbers == [1, 2]


def test_the_enemy_flag_is_understood():
    from highlighter.cli import CommandLine

    assert CommandLine.parse(["m.dem", "-enemy"]).enemy is True
    assert CommandLine.parse(["m.dem", "--enemy"]).enemy is True
    assert CommandLine.parse(["m.dem"]).enemy is False
