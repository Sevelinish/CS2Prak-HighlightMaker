from __future__ import annotations

from pathlib import Path

from conftest import make_kill, make_roster, make_round

from highlighter.config.schema import GameConfig, RecordingConfig
from highlighter.media.encoders import EncoderProfile
from highlighter.domain.highlight import Highlight, HighlightTag
from highlighter.plan.builder import RecordingPlanBuilder
from highlighter.recording.mirv_script import MirvScriptBuilder

SOFTWARE_ENCODER = EncoderProfile(
    codec="libx264",
    arguments=("-c:v", "libx264", "-preset", "faster", "-crf", "20", "-pix_fmt", "yuv420p"),
    container="mp4",
    is_hardware=False,
)

def build_highlight(round_, player, kills, codes=("kills_3",)):
    return Highlight(
        round_number=round_.number,
        player=player,
        side=round_.side_of(player.steam_id64),
        kills=tuple(kills),
        tags=tuple(HighlightTag(code, code, 10.0) for code in codes),
    )


def build_plan(match, terrorists, counter_terrorists, settings=None, tmp_path=Path(".")):
    roster = make_roster(terrorists, counter_terrorists)
    kills = [
        make_kill(5000, terrorists[0], counter_terrorists[0]),
        make_kill(5300, terrorists[0], counter_terrorists[1]),
    ]
    round_ = make_round(roster=roster, kills=kills, freeze_end_tick=4000, end_tick=9000)
    match.rounds.append(round_)
    highlight = build_highlight(round_, terrorists[0], kills)
    builder = RecordingPlanBuilder(settings or RecordingConfig())
    return builder.build(match, [highlight], tmp_path / "Highlighter")


def test_clip_bounds_apply_padding(match, terrorists, counter_terrorists):
    settings = RecordingConfig(lead_in_seconds=2.0, post_roll_seconds=1.0)
    plan = build_plan(match, terrorists, counter_terrorists, settings)
    clip = plan.clips[0]

    assert clip.start_tick == 5000 - 2 * match.tick_rate
    assert clip.end_tick == 5300 + 1 * match.tick_rate
    assert clip.action_start_tick == 5000
    assert clip.action_end_tick == 5300


def test_clip_bounds_never_leave_the_round(match, terrorists, counter_terrorists):
    settings = RecordingConfig(lead_in_seconds=600.0, post_roll_seconds=600.0)
    plan = build_plan(match, terrorists, counter_terrorists, settings)
    clip = plan.clips[0]

    assert clip.start_tick >= 4000
    assert clip.end_tick <= 9000


def test_clip_name_is_filesystem_safe(match, terrorists, counter_terrorists):
    terrorists[0] = type(terrorists[0])(terrorists[0].steam_id64, "-=[ Hé:llo ]=-")
    plan = build_plan(match, terrorists, counter_terrorists)

    assert all(character.isalnum() or character == "_" for character in plan.clips[0].name)


def test_plan_serialises_to_json_friendly_mapping(match, terrorists, counter_terrorists):
    plan = build_plan(match, terrorists, counter_terrorists)
    payload = plan.to_mapping()

    assert payload["version"] == 5
    assert payload["demo"]["map"] == "de_mirage"
    assert payload["demo"]["endTick"] > 0
    assert payload["recording"]["fps"] == 60
    assert isinstance(payload["clips"][0]["player"]["steamId64"], str)
    assert payload["clips"][0]["tags"] == ["kills_3"]
    assert payload["clips"][0]["segments"][0]["killTicks"] == [5000, 5300]


def test_account_id_is_derived_from_steam_id(match, terrorists, counter_terrorists):
    plan = build_plan(match, terrorists, counter_terrorists)
    clip = plan.clips[0]

    assert clip.player.account_id == clip.player.steam_id64 - 76561197960265728


def test_script_bundle_covers_every_clip(match, terrorists, counter_terrorists, tmp_path):
    plan = build_plan(match, terrorists, counter_terrorists, tmp_path=tmp_path)
    bundle = MirvScriptBuilder(
        RecordingConfig(), SOFTWARE_ENCODER, GameConfig(), tmp_path / "takes"
    ).build(plan)

    names = {script.name for script in bundle.files}

    assert bundle.entry_script == "highlighter_session"
    assert "highlighter_seek" in names
    assert "highlighter_c01_s01_start" in names
    assert "highlighter_c01_s01_end" in names


def test_session_script_schedules_each_boundary(match, terrorists, counter_terrorists, tmp_path):
    plan = build_plan(match, terrorists, counter_terrorists, tmp_path=tmp_path)
    bundle = MirvScriptBuilder(
        RecordingConfig(), SOFTWARE_ENCODER, GameConfig(), tmp_path / "takes"
    ).build(plan)
    session = next(script for script in bundle.files if script.name == "highlighter_session")
    clip = plan.clips[0]

    assert (
        f"mirv_cmd addAtTick {clip.start_tick} exec highlighter_c01_s01_start" in session.content
    )
    assert f"mirv_cmd addAtTick {clip.end_tick} exec highlighter_c01_s01_end" in session.content
    assert "mirv_streams record fps 60" in session.content
    assert "{QUOTE}{AFX_STREAM_PATH}/video.mp4{QUOTE}" in session.content


def test_screen_mode_enables_cs2_screen_capture(match, terrorists, counter_terrorists, tmp_path):
    settings = RecordingConfig(capture_mode="full")
    plan = build_plan(match, terrorists, counter_terrorists, settings, tmp_path=tmp_path)
    bundle = MirvScriptBuilder(
        settings, SOFTWARE_ENCODER, GameConfig(), tmp_path / "takes"
    ).build(plan)
    session = next(script for script in bundle.files if script.name == "highlighter_session")

    assert "mirv_streams record screen enabled 1" in session.content
    assert "mirv_streams record screen settings highlighterFfmpeg" in session.content
    assert "mirv_streams record startMovieWav 1" in session.content


def test_session_script_avoids_the_csgo_only_stream(match, terrorists, counter_terrorists, tmp_path):
    plan = build_plan(match, terrorists, counter_terrorists, tmp_path=tmp_path)
    bundle = MirvScriptBuilder(
        RecordingConfig(), SOFTWARE_ENCODER, GameConfig(), tmp_path / "takes"
    ).build(plan)
    session = next(script for script in bundle.files if script.name == "highlighter_session")

    assert "baseFx" not in session.content
    assert "mirv_streams edit baseFx" not in session.content


def test_ffmpeg_output_goes_inside_the_stream_folder(match, terrorists, counter_terrorists, tmp_path):
    plan = build_plan(match, terrorists, counter_terrorists, tmp_path=tmp_path)
    bundle = MirvScriptBuilder(
        RecordingConfig(), SOFTWARE_ENCODER, GameConfig(), tmp_path / "takes"
    ).build(plan)
    session = next(script for script in bundle.files if script.name == "highlighter_session")

    assert "{AFX_STREAM_PATH}/video.mp4" in session.content
    assert "{AFX_STREAM_PATH}.mp4" not in session.content


def test_last_clip_quits_the_game(match, terrorists, counter_terrorists, tmp_path):
    plan = build_plan(match, terrorists, counter_terrorists, tmp_path=tmp_path)
    bundle = MirvScriptBuilder(
        RecordingConfig(), SOFTWARE_ENCODER, GameConfig(), tmp_path / "takes"
    ).build(plan)
    end_script = next(
        script for script in bundle.files if script.name == "highlighter_c01_s01_end"
    )

    assert "mirv_streams record end" in end_script.content
    assert "quit" in end_script.content


def test_spectate_command_uses_account_id(match, terrorists, counter_terrorists, tmp_path):
    plan = build_plan(match, terrorists, counter_terrorists, tmp_path=tmp_path)
    bundle = MirvScriptBuilder(
        RecordingConfig(), SOFTWARE_ENCODER, GameConfig(), tmp_path / "takes"
    ).build(plan)
    start_script = next(
        script for script in bundle.files if script.name == "highlighter_c01_s01_start"
    )

    assert f"spec_lock_to_accountid {plan.clips[0].player.account_id}" in start_script.content
    assert "spec_mode 2" in start_script.content
