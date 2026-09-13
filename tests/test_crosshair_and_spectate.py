from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from conftest import make_kill, make_player, make_round

from highlighter.config.schema import CrosshairConfig, GameConfig, RecordingConfig
from highlighter.domain.highlight import Highlight, HighlightTag
from highlighter.media.crosshair import CrosshairFilterBuilder
from highlighter.media.encoders import EncoderProfile
from highlighter.plan.builder import RecordingPlanBuilder
from highlighter.recording.mirv_script import SPECTATOR_MODES, MirvScriptBuilder

ENABLED_CROSSHAIR = CrosshairConfig(enabled=True)
SOFTWARE_ENCODER = EncoderProfile(
    codec="libx264",
    arguments=("-c:v", "libx264"),
    container="mp4",
    is_hardware=False,
)


def start_script(match, player_name: str = "kulbergenn12", slot: int = 5) -> str:
    attacker = make_player(1, player_name).with_slot(slot)
    victim = make_player(11)
    kills = (make_kill(10_000, attacker, victim),)
    round_ = make_round(freeze_end_tick=0, end_tick=1_000_000, kills=list(kills))
    match.rounds.append(round_)

    highlight = Highlight(
        round_number=round_.number,
        player=attacker,
        side=None,
        kills=kills,
        tags=(HighlightTag("kills_2", "2K", 4.0),),
    )
    settings = RecordingConfig()
    plan = RecordingPlanBuilder(settings).build(match, [highlight], Path("out"))
    bundle = MirvScriptBuilder(
        settings, SOFTWARE_ENCODER, GameConfig(), Path("takes")
    ).build(plan)
    return next(item for item in bundle.files if item.name.endswith("_s01_start")).content


def test_a_spec_mode_is_set_before_the_camera_switches(match):
    lines = start_script(match).splitlines()

    first_mode = next(index for index, line in enumerate(lines) if line.startswith("spec_mode"))
    switch = next(index for index, line in enumerate(lines) if line.startswith("spec_player"))

    assert first_mode < switch


def test_camera_is_switched_by_slot_then_locked(match):
    lines = start_script(match, slot=5).splitlines()

    assert "spec_player 5" in lines
    lock = next(
        index for index, line in enumerate(lines) if line.startswith("spec_lock_to_accountid")
    )

    assert lines.index("spec_player 5") < lock


def test_auto_director_is_disabled_first(match):
    assert start_script(match).splitlines()[0] == "spec_autodirector 0"


def test_first_person_is_in_eye_not_roaming(match):
    lines = start_script(match).splitlines()

    assert "spec_mode 2" in lines
    assert "spec_mode 4" not in lines


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("fixed", 1), ("first_person", 2), ("third_person", 3), ("free", 4)],
)
def test_cs2_observer_mode_numbers(mode: str, expected: int):
    assert SPECTATOR_MODES[mode] == expected


def test_spectate_locks_by_account_id(match):
    attacker = make_player(1, "kulbergenn12")

    assert f"spec_lock_to_accountid {attacker.account_id}" in start_script(match)


@pytest.mark.parametrize("hostile", ['na"me', "na;me", "na\x00me"])
def test_console_breaking_characters_are_stripped(hostile: str):
    cleaned = MirvScriptBuilder._console_safe(hostile)

    assert '"' not in cleaned
    assert ";" not in cleaned
    assert all(character.isprintable() for character in cleaned)


def test_crosshair_overlay_is_off_by_default():
    assert CrosshairConfig().enabled is False
    assert CrosshairFilterBuilder(CrosshairConfig()).build() == ""


def test_crosshair_filter_has_four_arms_and_an_outline():
    chain = CrosshairFilterBuilder(ENABLED_CROSSHAIR).build()

    assert chain.count("drawbox=") == 8
    assert "color=black@1" in chain
    assert "color=0x00FF00@0.9" in chain


def test_dot_adds_a_fifth_box():
    without = CrosshairFilterBuilder(CrosshairConfig(enabled=True, dot=False)).build().count("drawbox=")
    with_dot = CrosshairFilterBuilder(CrosshairConfig(enabled=True, dot=True)).build().count("drawbox=")

    assert with_dot == without + 2


def test_crosshair_is_resolution_independent():
    chain = CrosshairFilterBuilder(ENABLED_CROSSHAIR).build()

    assert "iw" in chain
    assert "ih" in chain


def test_outline_can_be_turned_off():
    chain = CrosshairFilterBuilder(CrosshairConfig(enabled=True, outline=0)).build()

    assert chain.count("drawbox=") == 4
    assert "black" not in chain


def find_ffmpeg() -> Path | None:
    for root in (Path("dist/HighlighterCS2/tools/ffmpeg"), Path("tools/ffmpeg")):
        if root.is_dir():
            for candidate in root.rglob("ffmpeg.exe"):
                return candidate
    return None


def test_ffmpeg_accepts_the_generated_filter(tmp_path: Path):
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        pytest.skip("ffmpeg is not provisioned in this checkout")

    output = tmp_path / "frame.png"
    completed = subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=640x360",
            "-frames:v",
            "1",
            "-vf",
            CrosshairFilterBuilder(ENABLED_CROSSHAIR).build(),
            str(output),
        ],
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert output.stat().st_size > 0
