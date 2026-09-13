from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from highlighter.cli import CommandLine
from highlighter.config.schema import ApplicationConfig, RecordingConfig
from highlighter.media.assembler import AssembledClip
from highlighter.media.concat import ConcatMuxer
from highlighter.media.output_library import OutputLibrary
from highlighter.media.reel import ReelBuilder
from highlighter.plan.models import ClipPlayer, ClipSegment, ClipSpec

PLAYER = ClipPlayer(name="kul", steam_id64=76561198717658391, account_id=757392663, slot=5)


def make_clip(index: int, output: Path, seconds: float = 5.0) -> AssembledClip:
    spec = ClipSpec(
        index=index,
        name=f"{index:02d}_clip",
        round_number=index,
        player=PLAYER,
        tags=("kills_2",),
        score=12.0,
        segments=(ClipSegment(1, 0, 320, (100,), seconds),),
        action_start_tick=100,
        action_end_tick=200,
    )
    return AssembledClip(clip=spec, output=output, has_audio=True, segment_count=1)


@pytest.mark.parametrize("flag", ["-one-file", "--one-file"])
def test_both_spellings_of_the_flag_work(flag: str):
    assert CommandLine.parse(["match.dem", flag]).one_file is True


def test_the_flag_is_off_by_default():
    assert CommandLine.parse(["match.dem"]).one_file is False
    assert RecordingConfig().single_file is False


def test_the_flag_combines_with_a_dashed_player_name():
    arguments = CommandLine.parse(["match.dem", "-one-file", "-p", "-n1clxe"])

    assert arguments.one_file is True
    assert arguments.player == "-n1clxe"


def test_config_key_round_trips():
    restored = ApplicationConfig.from_mapping(
        ApplicationConfig(recording=RecordingConfig(single_file=True)).to_mapping()
    )

    assert restored.recording.single_file is True


def test_clips_stay_in_the_folder_root_by_default(tmp_path: Path):
    library = OutputLibrary(tmp_path, "match", "mp4")

    assert library.parts_directory == library.directory
    assert library.destination_for("01_clip").parent == library.directory


def test_single_file_mode_tucks_clips_into_parts(tmp_path: Path):
    library = OutputLibrary(tmp_path, "match", "mp4", single_file=True)

    assert library.parts_directory == library.directory / "parts"
    assert library.destination_for("01_clip").parent.name == "parts"
    assert library.reel_destination().parent == library.directory


def test_reel_is_named_after_the_demo(tmp_path: Path):
    library = OutputLibrary(tmp_path, "match", "mp4", single_file=True)

    assert library.reel_destination().name == "match_highlights.mp4"


def test_prepare_creates_the_parts_folder(tmp_path: Path):
    library = OutputLibrary(tmp_path, "match", "mp4", single_file=True)
    library.prepare()

    assert (tmp_path / "match" / "parts").is_dir()


def find_ffmpeg() -> Path | None:
    for root in (Path("dist/HighlighterCS2/tools/ffmpeg"), Path("tools/ffmpeg")):
        if root.is_dir():
            for candidate in root.rglob("ffmpeg.exe"):
                return candidate
    return None


def render_clip(ffmpeg: Path, target: Path, seconds: int, colour: str) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"color=c={colour}:s=320x180:r=30:d={seconds}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(target),
        ],
        check=True,
        capture_output=True,
    )
    return target


def probe_duration(ffmpeg: Path, video: Path) -> float:
    probe = ffmpeg.with_name("ffprobe.exe")
    completed = subprocess.run(
        [
            str(probe), "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(video),
        ],
        capture_output=True,
        text=True,
    )
    return float(completed.stdout.strip())


def test_three_clips_really_become_one_file(tmp_path: Path):
    ffmpeg = find_ffmpeg()
    if ffmpeg is None or not ffmpeg.with_name("ffprobe.exe").is_file():
        pytest.skip("ffmpeg is not provisioned in this checkout")

    library = OutputLibrary(tmp_path, "match", "mp4", single_file=True)
    library.prepare()

    clips = [
        make_clip(index, render_clip(ffmpeg, library.destination_for(f"{index:02d}_clip"), 1, colour))
        for index, colour in enumerate(("red", "green", "blue"), start=1)
    ]

    reel = ReelBuilder(ffmpeg, library).build(clips)

    assert reel is not None
    assert reel.clip_count == 3
    assert reel.output.is_file()
    assert reel.output.parent == library.directory
    assert probe_duration(ffmpeg, reel.output) == pytest.approx(3.0, abs=0.3)


def test_a_single_clip_is_moved_rather_than_re_encoded(tmp_path: Path):
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        pytest.skip("ffmpeg is not provisioned in this checkout")

    library = OutputLibrary(tmp_path, "match", "mp4", single_file=True)
    library.prepare()
    only = render_clip(ffmpeg, library.destination_for("01_clip"), 1, "red")
    original = only.read_bytes()

    reel = ReelBuilder(ffmpeg, library).build([make_clip(1, only)])

    assert reel is not None
    assert reel.output.read_bytes() == original
    assert not only.exists()


def test_building_a_reel_from_nothing_returns_none(tmp_path: Path):
    library = OutputLibrary(tmp_path, "match", "mp4", single_file=True)

    assert ReelBuilder(tmp_path / "ffmpeg.exe", library).build([]) is None


def test_concat_of_a_single_part_skips_ffmpeg(tmp_path: Path):
    only = tmp_path / "a.mp4"
    only.write_bytes(b"data")

    joined = ConcatMuxer(tmp_path / "missing-ffmpeg.exe").join([only], tmp_path / "out.mp4")

    assert joined == only


def test_concat_refuses_an_empty_list(tmp_path: Path):
    from highlighter.infrastructure.errors import EncodingError

    with pytest.raises(EncodingError):
        ConcatMuxer(tmp_path / "ffmpeg.exe").join([], tmp_path / "out.mp4")
