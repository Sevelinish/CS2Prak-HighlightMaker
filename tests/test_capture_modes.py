from __future__ import annotations

from pathlib import Path

import pytest
from conftest import make_kill, make_player, make_round

from highlighter.config.schema import GameConfig, RecordingConfig
from highlighter.domain.highlight import Highlight, HighlightTag
from highlighter.media.encoders import EncoderProfile
from highlighter.plan.builder import RecordingPlanBuilder
from highlighter.recording.mirv_script import MirvScriptBuilder

ENCODER = EncoderProfile("libx264", ("-c:v", "libx264"), "mp4", False)


def session(match, **overrides) -> str:
    settings = RecordingConfig(**overrides)
    attacker = make_player(1, "kul").with_slot(5)
    kills = (make_kill(10_000, attacker, make_player(11)),)
    round_ = make_round(freeze_end_tick=0, end_tick=1_000_000, kills=list(kills))
    match.rounds.append(round_)
    highlight = Highlight(round_.number, attacker, None, kills, (HighlightTag("k", "k", 1.0),))
    plan = RecordingPlanBuilder(settings).build(match, [highlight], Path("out"))
    bundle = MirvScriptBuilder(settings, ENCODER, GameConfig(), Path("takes")).build(plan)
    return next(item for item in bundle.files if item.name == "highlighter_session").content


def test_crosshair_mode_keeps_the_game_crosshair(match):
    content = session(match)

    assert "mirv_streams record screen enabled 1" in content
    assert "cl_drawhud 1" in content
    assert "cl_draw_only_deathnotices 1" in content


def test_crosshair_mode_never_blanks_the_hud(match):
    content = session(match)

    assert "cl_drawhud 0" not in content
    assert "crosshair 0" not in content


def test_killfeed_is_off_by_default(match):
    assert "cl_drawhud_force_deathnotices -1" in session(match)


def test_killfeed_can_be_kept(match):
    assert "cl_drawhud_force_deathnotices 1" in session(match, show_killfeed=True)


def test_clean_mode_still_removes_everything(match):
    content = session(match, capture_mode="clean")

    assert "capture beforeUi" in content
    assert "mirv_streams record screen enabled 0" in content
    assert "cl_draw_only_deathnotices" not in content


def test_full_mode_draws_the_normal_hud(match):
    content = session(match, capture_mode="full")

    assert "cl_draw_only_deathnotices 0" in content
    assert "cl_drawhud_force_deathnotices 0" in content
    assert "highlighterClean" not in content


@pytest.mark.parametrize("mode", ["crosshair", "clean", "full"])
def test_every_mode_configures_exactly_one_capture_path(match, mode: str):
    content = session(match, capture_mode=mode)

    uses_screen = "mirv_streams record screen enabled 1" in content
    uses_stream = "capture beforeUi" in content

    assert uses_screen != uses_stream
