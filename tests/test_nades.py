from __future__ import annotations

import math
from pathlib import Path

import pytest
from conftest import make_player, make_round

from highlighter.cli import CommandLine
from highlighter.config.schema import GameConfig, NadeConfig, RecordingConfig
from highlighter.domain.geometry import CameraPlacement, Vector3, ViewAngles
from highlighter.domain.grenade import Grenade, GrenadeKind
from highlighter.media.encoders import EncoderProfile
from highlighter.modes import RunMode, UnknownModeError
from highlighter.plan.nade_builder import NadePlanBuilder
from highlighter.recording.mirv_script import MirvScriptBuilder

ENCODER = EncoderProfile("libx264", ("-c:v", "libx264"), "mp4", False)


def make_grenade(
    throw_tick: int = 10_000,
    detonate_tick: int = 10_320,
    kind: GrenadeKind = GrenadeKind.SMOKE,
    place: str = "Window",
) -> Grenade:
    return Grenade(
        kind=kind,
        round_number=3,
        thrower=make_player(1, "kul").with_slot(5),
        side=None,
        throw_tick=throw_tick,
        detonate_tick=detonate_tick,
        thrower_position=Vector3(0.0, 0.0, 0.0),
        thrower_angles=ViewAngles(-10.0, 45.0),
        landing=Vector3(1000.0, 0.0, 0.0),
        landing_place=place,
        round_time_seconds=42.0,
    )


def build(match, grenades, nades: NadeConfig | None = None):
    match.rounds.append(make_round(number=3, freeze_end_tick=0, end_tick=1_000_000))
    return NadePlanBuilder(RecordingConfig(), nades or NadeConfig()).build(
        match, grenades, Path("out")
    )


def bundle_for(match, tmp_path):
    plan = build(match, [make_grenade()])
    bundle = MirvScriptBuilder(
        RecordingConfig(), ENCODER, GameConfig(), tmp_path / "takes"
    ).build(plan)
    return plan, bundle


@pytest.mark.parametrize(
    ("token", "label"),
    [
        ("nades_smoke", "smoke"),
        ("nades_flash", "flash"),
        ("nades_he", "he"),
        ("nades_molotov", "molotov"),
        ("nades_decoy", "decoy"),
    ],
)
def test_each_grenade_mode_selects_one_kind(token: str, label: str):
    mode = RunMode.parse(token)

    assert tuple(kind.label for kind in mode.grenade_kinds) == (label,)
    assert mode.records_grenades is True


def test_plain_nades_covers_every_kind():
    assert len(RunMode.parse("nades").grenade_kinds) == len(GrenadeKind)


def test_no_mode_means_highlights_and_no_grenades():
    mode = RunMode.parse(None)

    assert mode.records_grenades is False
    assert mode.grenade_kinds == ()


def test_highlights_token_is_accepted():
    assert RunMode.parse("highlights").records_grenades is False


def test_an_unknown_mode_lists_the_options():
    with pytest.raises(UnknownModeError, match="nades_smoke"):
        RunMode.parse("nades_banana")


def test_aliases_are_understood():
    assert RunMode.parse("nades_molly").grenade_kinds == (GrenadeKind.MOLOTOV,)
    assert RunMode.parse("nades_flashbang").grenade_kinds == (GrenadeKind.FLASH,)


def test_the_mode_flag_reaches_the_parser():
    assert CommandLine.parse(["m.dem", "-m", "nades_smoke"]).mode == "nades_smoke"
    assert CommandLine.parse(["m.dem"]).mode is None


def test_every_kind_maps_to_an_event_and_a_projectile():
    for kind in GrenadeKind:
        assert kind.detonate_event.endswith(("detonate", "startburn", "started"))
        assert kind.projectile_class.endswith("Projectile")


def test_camera_sits_between_the_landing_and_the_thrower():
    camera = CameraPlacement.looking_at(
        target=Vector3(1000.0, 0.0, 0.0),
        from_side=Vector3(0.0, 0.0, 0.0),
        distance=200.0,
        height=50.0,
    )

    assert camera.position.x == pytest.approx(800.0)
    assert camera.position.z == pytest.approx(50.0)


def test_camera_looks_at_the_landing_point():
    target = Vector3(1000.0, 250.0, -30.0)
    camera = CameraPlacement.looking_at(target, Vector3(0.0, 0.0, 0.0), 220.0, 90.0)
    expected = camera.position.angles_towards(target)

    assert camera.angles.pitch == pytest.approx(expected.pitch)
    assert camera.angles.yaw == pytest.approx(expected.yaw)


def test_a_camera_above_the_target_looks_down():
    camera = CameraPlacement.looking_at(
        Vector3(500.0, 0.0, 0.0), Vector3(0.0, 0.0, 0.0), 200.0, 100.0
    )

    assert camera.angles.pitch > 0


def test_distance_from_the_landing_is_respected():
    target = Vector3(1000.0, 0.0, 0.0)
    camera = CameraPlacement.looking_at(target, Vector3(0.0, 0.0, 0.0), 300.0, 0.0)

    assert camera.position.distance_to(target) == pytest.approx(300.0)


def test_a_degenerate_direction_does_not_explode():
    same = Vector3(5.0, 5.0, 5.0)

    camera = CameraPlacement.looking_at(same, same, 100.0, 10.0)

    assert math.isfinite(camera.angles.pitch)
    assert math.isfinite(camera.angles.yaw)


def test_the_clip_starts_the_configured_lead_in_before_the_throw(match):
    plan = build(match, [make_grenade()])

    assert plan.clips[0].segments[0].start_tick == 10_000 - 3 * match.tick_rate


def test_the_clip_holds_on_the_landing(match):
    plan = build(match, [make_grenade()])

    assert plan.clips[0].segments[0].end_tick == 10_320 + 3 * match.tick_rate


def test_the_zoom_beat_lands_before_the_throw(match):
    plan = build(match, [make_grenade()])
    zoom = next(b for b in plan.clips[0].beats if b.name == "zoom")

    assert zoom.tick == 10_000 - int(1.0 * match.tick_rate)
    assert "mirv_fov 22.5" in zoom.commands


def test_the_zoom_hold_lasts_real_demo_time(match):
    plan = build(match, [make_grenade()])
    beats = {b.name: b for b in plan.clips[0].beats}

    held = beats["unzoom"].tick - beats["zoom"].tick

    assert held == int(1.0 * match.tick_rate)


def test_the_zoom_hold_length_follows_the_setting(match):
    settings = NadeConfig(freeze_seconds=1.5)
    plan = build(match, [make_grenade()], settings)
    beats = {b.name: b for b in plan.clips[0].beats}

    assert beats["unzoom"].tick - beats["zoom"].tick == int(1.5 * match.tick_rate)


def test_no_timescale_command_is_emitted(match):
    plan = build(match, [make_grenade()])

    for beat in plan.clips[0].beats:
        assert not any("timescale" in command for command in beat.commands)


def test_the_unzoom_restores_the_default_fov(match):
    plan = build(match, [make_grenade()])
    beats = {b.name: b for b in plan.clips[0].beats}

    assert "mirv_fov default" in beats["unzoom"].commands
    assert beats["unzoom"].tick > beats["zoom"].tick


def test_the_landing_beat_frees_the_camera_then_teleports(match):
    plan = build(match, [make_grenade()])
    landing = next(b for b in plan.clips[0].beats if b.name == "landing")

    assert landing.commands[0] == "spec_mode 4"
    assert landing.commands[1].startswith("spec_goto ")


def test_the_cut_to_the_landing_happens_shortly_after_the_throw(match):
    plan = build(match, [make_grenade()])
    landing = next(b for b in plan.clips[0].beats if b.name == "landing")

    assert landing.tick == 10_000 + int(0.5 * match.tick_rate)


def test_the_cut_never_waits_past_the_detonation(match):
    plan = build(match, [make_grenade(throw_tick=10_000, detonate_tick=10_010)])
    landing = next(b for b in plan.clips[0].beats if b.name == "landing")

    assert landing.tick == 10_010


def test_beats_are_ordered_through_the_clip(match):
    plan = build(match, [make_grenade()])
    ticks = [beat.tick for beat in plan.clips[0].beats]

    assert ticks == sorted(ticks)


def test_the_clip_name_carries_the_place_and_kind(match):
    plan = build(match, [make_grenade(place="Window")])

    assert "smoke" in plan.clips[0].name
    assert "window" in plan.clips[0].name


def test_the_plan_records_the_spot_and_the_throw_commands(match):
    plan = build(match, [make_grenade(place="Window")])
    note = plan.clips[0].note

    assert note.startswith("smoke into Window")
    assert "setpos " in note
    assert "setang " in note
    assert plan.clips[0].to_mapping()["note"] == note


def test_beats_survive_serialisation(match):
    plan = build(match, [make_grenade()])
    payload = plan.clips[0].to_mapping()

    assert len(payload["beats"]) == 3
    assert payload["beats"][0]["name"] == "zoom"


def test_the_script_builder_schedules_every_beat(match, tmp_path):
    _, bundle = bundle_for(match, tmp_path)
    session = next(f for f in bundle.files if f.name == "highlighter_session").content

    for name in ("zoom", "unzoom", "landing"):
        assert f"exec highlighter_c01_{name}" in session


def test_each_beat_gets_its_own_script(match, tmp_path):
    _, bundle = bundle_for(match, tmp_path)
    names = {item.name for item in bundle.files}

    assert "highlighter_c01_zoom" in names
    assert "highlighter_c01_unzoom" in names
    assert "highlighter_c01_landing" in names


def test_the_landing_script_holds_the_spec_goto(match, tmp_path):
    _, bundle = bundle_for(match, tmp_path)
    landing = next(f for f in bundle.files if f.name == "highlighter_c01_landing")

    assert "spec_goto" in landing.content
    assert landing.content.splitlines()[0] == "spec_mode 4"


def test_highlight_clips_carry_no_beats(match, terrorists, counter_terrorists):
    from conftest import make_kill, make_roster

    from highlighter.domain.highlight import Highlight, HighlightTag
    from highlighter.plan.builder import RecordingPlanBuilder

    kills = (make_kill(5000, terrorists[0], counter_terrorists[0]),)
    round_ = make_round(roster=make_roster(terrorists, counter_terrorists), kills=list(kills))
    match.rounds.append(round_)
    highlight = Highlight(
        round_.number, terrorists[0], None, kills, (HighlightTag("k", "k", 1.0),)
    )

    plan = RecordingPlanBuilder(RecordingConfig()).build(match, [highlight], Path("out"))
    bundle = MirvScriptBuilder(
        RecordingConfig(), ENCODER, GameConfig(), Path("takes")
    ).build(plan)

    assert plan.clips[0].beats == ()
    assert not any("_zoom" in item.name for item in bundle.files)
