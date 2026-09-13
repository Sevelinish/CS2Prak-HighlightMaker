from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import make_kill, make_roster, make_round

from highlighter.config.schema import GameConfig, RecordingConfig
from highlighter.media.encoders import EncoderProfile
from highlighter.domain.highlight import Highlight, HighlightTag
from highlighter.infrastructure.errors import RecordingError
from highlighter.plan.builder import RecordingPlanBuilder
from highlighter.plan.writer import RecordingPlanWriter
from highlighter.recording.mirv_script import MirvScriptBuilder
from highlighter.recording.script_writer import ScriptWriter

SOFTWARE_ENCODER = EncoderProfile(
    codec="libx264",
    arguments=("-c:v", "libx264", "-preset", "faster", "-crf", "20", "-pix_fmt", "yuv420p"),
    container="mp4",
    is_hardware=False,
)

@pytest.fixture
def plan(match, terrorists, counter_terrorists, tmp_path: Path):
    kills = [
        make_kill(5000, terrorists[0], counter_terrorists[0]),
        make_kill(5300, terrorists[0], counter_terrorists[1]),
    ]
    round_ = make_round(
        roster=make_roster(terrorists, counter_terrorists),
        kills=kills,
        freeze_end_tick=4000,
        end_tick=9000,
    )
    match.rounds.append(round_)
    highlight = Highlight(
        round_number=round_.number,
        player=terrorists[0],
        side=round_.side_of(terrorists[0].steam_id64),
        kills=tuple(kills),
        tags=(HighlightTag("kills_2", "2K", 4.0),),
    )
    return RecordingPlanBuilder(RecordingConfig()).build(
        match, [highlight], tmp_path / "Highlighter"
    )


@pytest.fixture
def bundle(plan, tmp_path: Path):
    return MirvScriptBuilder(
        RecordingConfig(), SOFTWARE_ENCODER, GameConfig(), tmp_path / "takes"
    ).build(plan)


def test_writes_every_script_to_the_config_directory(bundle, tmp_path: Path):
    config_directory = tmp_path / "cfg"
    config_directory.mkdir()

    written = ScriptWriter(config_directory).write(bundle)

    assert len(written) == len(bundle.files)
    assert all(path.is_file() for path in written)
    assert (config_directory / "highlighter_session.cfg").is_file()


def test_mirrors_scripts_for_inspection(bundle, tmp_path: Path):
    config_directory = tmp_path / "cfg"
    config_directory.mkdir()
    mirror = tmp_path / "work" / "scripts"

    ScriptWriter(config_directory, mirror).write(bundle)

    assert (mirror / "highlighter_session.cfg").is_file()


def test_cleanup_removes_only_generated_scripts(bundle, tmp_path: Path):
    config_directory = tmp_path / "cfg"
    config_directory.mkdir()
    user_config = config_directory / "autoexec.cfg"
    user_config.write_text("bind x noclip", encoding="utf-8")

    writer = ScriptWriter(config_directory)
    writer.write(bundle)
    writer.cleanup()

    assert not list(config_directory.glob("highlighter_*.cfg"))
    assert user_config.read_text(encoding="utf-8") == "bind x noclip"


def test_rewriting_clears_scripts_from_a_previous_run(bundle, tmp_path: Path):
    config_directory = tmp_path / "cfg"
    config_directory.mkdir()
    stale = config_directory / "highlighter_c99_start.cfg"
    stale.write_text("stale", encoding="utf-8")

    ScriptWriter(config_directory).write(bundle)

    assert not stale.exists()


def test_missing_config_directory_raises(bundle, tmp_path: Path):
    with pytest.raises(RecordingError):
        ScriptWriter(tmp_path / "does_not_exist").write(bundle)


def test_plan_writer_produces_readable_json(plan, tmp_path: Path):
    destination = RecordingPlanWriter(tmp_path / "plans").write(plan)
    payload = json.loads(destination.read_text(encoding="utf-8"))

    assert destination.name.endswith(".json")
    assert payload["clips"][0]["roundNumber"] == 1
    assert payload["demo"]["tickRate"] == 64
