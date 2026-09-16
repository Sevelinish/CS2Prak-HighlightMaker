from __future__ import annotations

import math
from pathlib import Path
from xml.etree import ElementTree

import pytest

from highlighter.config.schema import GameConfig, NadeConfig, RecordingConfig
from highlighter.domain.chase import ChaseCameraDirector, ChasePath
from highlighter.domain.flight import FlightPoint, GrenadeFlight
from highlighter.domain.geometry import Vector3, ViewAngles
from highlighter.domain.grenade import Grenade, GrenadeKind
from highlighter.domain.match import Match
from highlighter.domain.player import Player
from highlighter.domain.round import Round
from highlighter.media.encoders import EncoderProfile
from highlighter.plan.nade_builder import NadePlanBuilder
from highlighter.recording.campath import CampathDocument
from highlighter.recording.mirv_script import MirvScriptBuilder

ENCODER = EncoderProfile("libx264", ("-c:v", "libx264"), "mp4", False)
TICK_RATE = 64
ARC = (
    (0.0, 0.0, 0.0),
    (60.0, 0.0, 70.0),
    (140.0, 0.0, 120.0),
    (230.0, 0.0, 150.0),
    (320.0, 0.0, 150.0),
    (410.0, 0.0, 120.0),
    (480.0, 0.0, 60.0),
    (520.0, 0.0, 10.0),
    (520.0, 0.0, 5.0),
    (520.0, 0.0, 5.0),
)


def arc_flight(first_tick: int = 1000) -> GrenadeFlight:
    return GrenadeFlight.of(
        [FlightPoint(first_tick + index * 4, Vector3(*point)) for index, point in enumerate(ARC)]
    )


def director(distance: float = 110.0, height: float = 20.0, stride: int = 1):
    return ChaseCameraDirector(distance, height, stride, TICK_RATE)


def test_a_flight_becomes_a_camera_path():
    path = director().follow(arc_flight())

    assert path.is_usable is True
    assert len(path.keyframes) >= 4


def test_the_path_starts_at_the_first_moving_tick():
    path = director().follow(arc_flight(first_tick=5000))

    assert path.start_tick == 5000
    assert path.keyframes[0].seconds == 0.0


def test_the_path_runs_forwards_in_time():
    times = [keyframe.seconds for keyframe in director().follow(arc_flight()).keyframes]

    assert times == sorted(times)
    assert len(set(times)) == len(times)


def test_the_camera_trails_the_grenade_at_the_asked_for_distance():
    flight = arc_flight()
    path = director(distance=110.0, height=0.0).follow(flight)
    moving = {point.tick: point.position for point in flight.moving()}

    gaps = []
    for keyframe in path.keyframes:
        tick = path.start_tick + round(keyframe.seconds * TICK_RATE)
        target = moving.get(tick)
        if target is not None:
            gaps.append(keyframe.placement.position.distance_to(target))

    assert gaps
    assert all(40.0 <= gap <= 140.0 for gap in gaps)


def test_the_camera_never_sits_on_top_of_the_grenade():
    flight = arc_flight()
    path = director(height=0.0).follow(flight)
    first = path.keyframes[0].placement.position

    assert first.distance_to(Vector3(*ARC[0])) > 50.0


def test_the_first_keyframe_sits_behind_the_throw():
    path = director(height=0.0).follow(arc_flight())

    assert path.keyframes[0].placement.position.x < 0.0


def test_the_camera_is_raised_by_the_setting():
    flat = director(height=0.0).follow(arc_flight()).keyframes[0].placement.position
    raised = director(height=40.0).follow(arc_flight()).keyframes[0].placement.position

    assert raised.z - flat.z == pytest.approx(40.0)


def test_every_keyframe_looks_at_the_grenade():
    flight = arc_flight()
    path = director().follow(flight)
    moving = {point.tick: point.position for point in flight.moving()}

    for keyframe in path.keyframes:
        tick = path.start_tick + round(keyframe.seconds * TICK_RATE)
        target = moving.get(tick)
        if target is None:
            continue
        wanted = keyframe.placement.position.angles_towards(target)
        assert keyframe.placement.angles.pitch == pytest.approx(wanted.pitch)
        assert keyframe.placement.angles.yaw == pytest.approx(wanted.yaw)


def test_the_path_holds_still_after_the_last_sample():
    path = director().follow(arc_flight(), hold_seconds=3.0)

    assert path.keyframes[-1].placement.position == path.keyframes[-2].placement.position
    assert path.keyframes[-1].seconds - path.keyframes[-2].seconds == pytest.approx(3.0)


def test_a_grenade_that_never_moved_has_no_path():
    still = GrenadeFlight.of(
        [FlightPoint(index, Vector3(10.0, 10.0, 10.0)) for index in range(20)]
    )

    assert director().follow(still).is_usable is False


def test_a_flight_with_too_few_samples_has_no_path():
    short = GrenadeFlight.of([FlightPoint(0, Vector3(0.0, 0.0, 0.0)), FlightPoint(4, Vector3(9.0, 0.0, 0.0))])

    assert director(stride=8).follow(short).is_usable is False


def test_a_coarser_stride_makes_fewer_keyframes():
    fine = len(director(stride=1).follow(arc_flight()).keyframes)
    coarse = len(director(stride=4).follow(arc_flight()).keyframes)

    assert coarse < fine


def make_match() -> Match:
    match = Match(demo_path=Path("m.dem"), map_name="de_mirage", tick_rate=TICK_RATE)
    match.rounds.append(
        Round(number=3, freeze_end_tick=0, end_tick=60_000, winner=None, end_reason=None)
    )
    return match


def smoke(first_tick: int = 1000, detonate: int = 1640) -> Grenade:
    return Grenade(
        kind=GrenadeKind.SMOKE,
        round_number=3,
        thrower=Player(76561198000000000, "kul", 5),
        side=None,
        throw_tick=first_tick,
        detonate_tick=detonate,
        thrower_position=Vector3(0.0, 0.0, 0.0),
        thrower_angles=ViewAngles(0.0, 0.0),
        landing=Vector3(520.0, 0.0, 5.0),
        landing_place="Window",
        flight=arc_flight(first_tick),
    )


def build(nades: NadeConfig, grenades=None):
    return NadePlanBuilder(RecordingConfig(), nades).build(
        make_match(), grenades or [smoke()], Path("out")
    )


def test_the_plan_carries_the_path_only_in_fly_mode():
    assert build(NadeConfig(follow_flight=True, fly_sample_stride=1)).clips[0].camera_path.is_usable is True
    assert build(NadeConfig()).clips[0].camera_path.is_usable is False


def test_fly_mode_films_the_flight_in_one_take():
    flying = build(NadeConfig(follow_flight=True, fly_sample_stride=1)).clips[0]
    cut = build(NadeConfig()).clips[0]

    assert len(flying.segments) == 1
    assert len(cut.segments) == 2


def test_fly_mode_drops_the_landing_teleport():
    beats = build(NadeConfig(follow_flight=True, fly_sample_stride=1)).clips[0].beats

    assert [beat.name for beat in beats] == ["zoom", "unzoom"]


def test_fly_mode_keeps_the_zoom_hold_before_the_throw():
    beats = build(NadeConfig(follow_flight=True, fly_sample_stride=1)).clips[0].beats

    assert beats[0].tick < 1000


def test_the_note_says_the_camera_flies():
    note = build(NadeConfig(follow_flight=True, fly_sample_stride=1)).clips[0].note

    assert "camera flies behind it" in note


def scripts(nades: NadeConfig):
    plan = build(nades)
    bundle = MirvScriptBuilder(
        RecordingConfig(), ENCODER, GameConfig(), Path("takes"), Path("C:/cs2/cfg")
    ).build(plan)
    return plan, bundle


def test_the_campath_is_written_next_to_the_scripts():
    _, bundle = scripts(NadeConfig(follow_flight=True, fly_sample_stride=1))
    names = {item.file_name for item in bundle.files}

    assert "highlighter_c01_fly.xml" in names
    assert "highlighter_c01_flycam.cfg" in names


def test_the_campath_is_loaded_and_enabled_at_the_throw():
    plan, bundle = scripts(NadeConfig(follow_flight=True, fly_sample_stride=1))
    session = next(f for f in bundle.files if f.name == "highlighter_session").content
    loader = next(f for f in bundle.files if f.name == "highlighter_c01_flycam").content

    assert f"addAtTick {plan.clips[0].camera_path.start_tick} exec highlighter_c01_flycam" in session
    assert loader.splitlines() == [
        "mirv_campath clear",
        'mirv_campath load "C:/cs2/cfg/highlighter_c01_fly.xml"',
        "mirv_campath offset current#0",
        "mirv_campath enabled 1",
    ]


def test_the_campath_is_switched_off_when_the_take_ends():
    _, bundle = scripts(NadeConfig(follow_flight=True, fly_sample_stride=1))
    end = next(f for f in bundle.files if f.name.endswith("_s01_end")).content

    assert "mirv_campath enabled 0" in end
    assert "mirv_campath clear" in end


def test_no_campath_is_written_without_the_flag():
    _, bundle = scripts(NadeConfig())

    assert not any(item.file_name.endswith(".xml") for item in bundle.files)
    assert not any("campath" in item.content for item in bundle.files)


def test_the_campath_document_matches_the_hlae_schema():
    path = director().follow(arc_flight(), hold_seconds=3.0)
    root = ElementTree.fromstring(CampathDocument.render(path))

    assert root.tag == "campath"
    assert root.get("positionInterp") == "cubic"
    assert root.get("rotationInterp") == "sCubic"
    assert root.get("fovInterp") == "cubic"

    points = root.find("points").findall("p")
    assert len(points) == len(path.keyframes)
    assert sorted(points[0].keys()) == ["fov", "rx", "ry", "rz", "t", "x", "y", "z"]


def test_the_document_writes_pitch_and_yaw_the_way_hlae_names_them():
    path = director().follow(arc_flight())
    points = ElementTree.fromstring(CampathDocument.render(path)).find("points").findall("p")
    keyframe = path.keyframes[1]

    assert float(points[1].get("ry")) == pytest.approx(keyframe.placement.angles.pitch, abs=0.01)
    assert float(points[1].get("rz")) == pytest.approx(keyframe.placement.angles.yaw, abs=0.01)
    assert points[1].get("rx") == "0"


def test_the_fly_flag_is_understood():
    from highlighter.cli import CommandLine

    assert CommandLine.parse(["m.dem", "-m", "nades_smoke", "-fly"]).fly is True
    assert CommandLine.parse(["m.dem", "--fly"]).fly is True
    assert CommandLine.parse(["m.dem"]).fly is False


def spawn_match(freeze_end: int = 10_000, previous_end: int = 8_720) -> Match:
    match = Match(demo_path=Path("m.dem"), map_name="de_ancient", tick_rate=TICK_RATE)
    match.rounds.append(
        Round(number=2, freeze_end_tick=previous_end, end_tick=previous_end, winner=None, end_reason=None)
    )
    match.rounds.append(
        Round(number=3, freeze_end_tick=freeze_end, end_tick=60_000, winner=None, end_reason=None)
    )
    return match


def thrown_at(tick: int, round_time: float) -> Grenade:
    grenade = smoke(first_tick=tick, detonate=tick + 640)
    return Grenade(
        kind=grenade.kind,
        round_number=3,
        thrower=grenade.thrower,
        side=None,
        throw_tick=tick,
        detonate_tick=tick + 640,
        thrower_position=grenade.thrower_position,
        thrower_angles=grenade.thrower_angles,
        landing=grenade.landing,
        landing_place="TSideUpper",
        round_time_seconds=round_time,
        flight=grenade.flight,
    )


def plan_for(grenade: Grenade, nades: NadeConfig | None = None):
    return NadePlanBuilder(RecordingConfig(), nades or NadeConfig()).build(
        spawn_match(), [grenade], Path("out")
    )


def test_a_throw_right_out_of_spawn_is_recognised():
    assert thrown_at(10_033, 0.52).thrown_from_spawn(4.0) is True
    assert thrown_at(15_000, 42.0).thrown_from_spawn(4.0) is False


def test_a_spawn_throw_is_filmed_from_inside_the_freeze_time():
    clip = plan_for(thrown_at(10_033, 0.52)).clips[0]
    start = clip.segments[0].start_tick

    assert start < 10_000
    assert (10_000 - start) / TICK_RATE > 4.0


def test_a_spawn_throw_gets_the_longer_run_up():
    clip = plan_for(thrown_at(10_033, 0.52)).clips[0]
    lead = (clip.action_start_tick - clip.segments[0].start_tick) / TICK_RATE

    assert lead == pytest.approx(NadeConfig().spawn_lead_seconds, abs=0.05)


def test_a_spawn_throw_never_reaches_into_the_round_before():
    clip = plan_for(thrown_at(10_033, 0.52)).clips[0]

    assert clip.segments[0].start_tick >= 8_720


def test_a_short_freeze_time_clamps_the_run_up():
    match = spawn_match(freeze_end=10_000, previous_end=9_900)
    plan = NadePlanBuilder(RecordingConfig(), NadeConfig()).build(
        match, [thrown_at(10_033, 0.52)], Path("out")
    )

    assert plan.clips[0].segments[0].start_tick >= 9_900


def test_a_mid_round_throw_still_starts_after_the_freeze_time():
    clip = plan_for(thrown_at(20_000, 156.0)).clips[0]

    assert clip.segments[0].start_tick >= 10_000


def test_a_mid_round_throw_keeps_the_normal_run_up():
    clip = plan_for(thrown_at(20_000, 156.0)).clips[0]
    lead = (clip.action_start_tick - clip.segments[0].start_tick) / TICK_RATE

    assert lead == pytest.approx(NadeConfig().lead_in_seconds, abs=0.05)


def test_the_spawn_window_is_configurable():
    narrow = NadeConfig(spawn_window_seconds=0.1)
    clip = plan_for(thrown_at(10_033, 0.52), narrow).clips[0]

    assert clip.segments[0].start_tick >= 10_000
