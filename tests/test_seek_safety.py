from __future__ import annotations

import re
from pathlib import Path

import pytest
from conftest import TICK_RATE, make_kill, make_player, make_round

from highlighter.config.schema import GameConfig, RecordingConfig
from highlighter.domain.highlight import Highlight, HighlightTag
from highlighter.media.encoders import EncoderProfile
from highlighter.plan.builder import RecordingPlanBuilder
from highlighter.plan.segmenter import ClipSegmenter
from highlighter.recording.mirv_script import BOOTSTRAP_TICK, MirvScriptBuilder

SOFTWARE_ENCODER = EncoderProfile(
    codec="libx264",
    arguments=("-c:v", "libx264"),
    container="mp4",
    is_hardware=False,
)
GOTOTICK_PATTERN = re.compile(r"demo_gototick (\d+)")
ADD_AT_TICK_PATTERN = re.compile(r"mirv_cmd addAtTick (\d+) exec (\S+)")


def build_bundle(match, kill_offsets_seconds: list[float], settings: RecordingConfig | None = None):
    settings = settings or RecordingConfig()
    attacker, victim = make_player(1), make_player(11)
    base = 10_000
    kills = tuple(
        make_kill(base + int(round(offset * TICK_RATE)), attacker, victim)
        for offset in kill_offsets_seconds
    )
    round_ = make_round(freeze_end_tick=0, end_tick=1_000_000, kills=list(kills))
    match.rounds.append(round_)

    highlight = Highlight(
        round_number=round_.number,
        player=attacker,
        side=None,
        kills=kills,
        tags=(HighlightTag("kills_3", "3K", 12.0),),
    )
    plan = RecordingPlanBuilder(settings).build(match, [highlight], Path("out"))
    return MirvScriptBuilder(settings, SOFTWARE_ENCODER, GameConfig(), Path("takes")).build(plan)


def seek_targets(bundle, script_name: str) -> list[int]:
    script = next((item for item in bundle.files if item.name == script_name), None)
    if script is None:
        return []
    return [int(value) for value in GOTOTICK_PATTERN.findall(script.content)]


@pytest.mark.parametrize("gap", [5.6, 6.0, 6.5, 7.0, 7.4, 7.6, 9.0, 20.0, 60.0])
def test_no_segment_ever_seeks_backwards(match, gap: float):
    bundle = build_bundle(match, [0.0, gap])
    session = next(item for item in bundle.files if item.name == "highlighter_session")

    schedule = {name: int(tick) for tick, name in ADD_AT_TICK_PATTERN.findall(session.content)}
    for name, fires_at in schedule.items():
        for destination in seek_targets(bundle, name):
            assert destination > fires_at, (
                f"{name} fires at tick {fires_at} but seeks back to {destination}"
            )


def test_the_six_second_gap_that_used_to_loop_is_safe(match):
    bundle = build_bundle(match, [0.0, 6.0])
    session = next(item for item in bundle.files if item.name == "highlighter_session")
    schedule = {name: int(tick) for tick, name in ADD_AT_TICK_PATTERN.findall(session.content)}

    for name, fires_at in schedule.items():
        assert all(target > fires_at for target in seek_targets(bundle, name))


def test_bootstrap_seek_is_dropped_when_it_would_go_backwards(match):
    bundle = build_bundle(match, [0.0])
    plan_start = min(
        int(tick) for tick, _ in ADD_AT_TICK_PATTERN.findall(
            next(item for item in bundle.files if item.name == "highlighter_session").content
        )
    )

    assert plan_start == BOOTSTRAP_TICK
    for destination in seek_targets(bundle, "highlighter_seek"):
        assert destination > BOOTSTRAP_TICK


def test_early_first_segment_emits_no_bootstrap_seek(match):
    settings = RecordingConfig(seek_lead_ticks=100_000)
    bundle = build_bundle(match, [0.0], settings)

    assert seek_targets(bundle, "highlighter_seek") == []


def test_split_threshold_accounts_for_the_seek_lead(match):
    settings = RecordingConfig()
    segmenter = ClipSegmenter(settings, match)
    attacker, victim = make_player(1), make_player(11)

    threshold_seconds = (
        settings.gap_hold_seconds
        + settings.resume_lead_seconds
        + settings.seek_lead_ticks / TICK_RATE
    )
    just_under = tuple(
        make_kill(10_000 + int(round(offset * TICK_RATE)), attacker, victim)
        for offset in (0.0, threshold_seconds - 0.5)
    )
    just_over = tuple(
        make_kill(10_000 + int(round(offset * TICK_RATE)), attacker, victim)
        for offset in (0.0, threshold_seconds + 0.5)
    )
    roomy = make_round(freeze_end_tick=0, end_tick=1_000_000)

    assert len(segmenter.segment(just_under, roomy)) == 1
    assert len(segmenter.segment(just_over, roomy)) == 2


def test_start_script_disables_the_auto_director_before_locking(match):
    bundle = build_bundle(match, [0.0])
    start = next(item for item in bundle.files if item.name.endswith("_s01_start"))
    lines = start.content.splitlines()

    assert lines[0] == "spec_autodirector 0"
    assert any(line.startswith("spec_lock_to_accountid") for line in lines)
    assert lines.index("spec_autodirector 0") < next(
        index for index, line in enumerate(lines) if line.startswith("spec_lock_to_accountid")
    )


def test_clean_mode_captures_before_the_panorama_ui(match):
    bundle = build_bundle(match, [0.0], RecordingConfig(capture_mode="clean"))
    session = next(item for item in bundle.files if item.name == "highlighter_session")

    assert "mirv_streams add normal highlighterClean" in session.content
    assert "mirv_streams edit highlighterClean capture beforeUi" in session.content
    assert "mirv_streams edit highlighterClean record 1" in session.content
    assert "mirv_streams record screen enabled 0" in session.content


def test_clean_mode_never_enables_the_ui_bearing_screen_capture(match):
    bundle = build_bundle(match, [0.0], RecordingConfig(capture_mode="clean"))
    session = next(item for item in bundle.files if item.name == "highlighter_session")

    assert "mirv_streams record screen enabled 1" not in session.content


def test_screen_mode_keeps_the_game_ui(match):
    settings = RecordingConfig(capture_mode="full")
    bundle = build_bundle(match, [0.0], settings)
    session = next(item for item in bundle.files if item.name == "highlighter_session")

    assert "mirv_streams record screen enabled 1" in session.content
    assert "highlighterClean" not in session.content


def test_stream_name_is_alphanumeric_as_hlae_requires(match):
    from highlighter.recording.mirv_script import CLEAN_STREAM_NAME

    assert CLEAN_STREAM_NAME.isalnum()
