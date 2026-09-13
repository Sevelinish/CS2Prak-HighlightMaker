from __future__ import annotations

from pathlib import Path

import pytest

from highlighter.cli import CommandLine
from highlighter.demo.locator import DemoLocator


@pytest.mark.parametrize("flag", ["-p", "--player", "--player-name"])
def test_a_name_starting_with_a_dash_is_accepted(flag: str):
    arguments = CommandLine.parse(["match.dem", flag, "-n1clxe"])

    assert arguments.player == "-n1clxe"
    assert arguments.demo == "match.dem"


def test_an_ordinary_name_still_works():
    assert CommandLine.parse(["match.dem", "-p", "s1mple"]).player == "s1mple"


def test_a_steam_id_still_works():
    arguments = CommandLine.parse(["match.dem", "-p", "76561198000000000"])

    assert arguments.player == "76561198000000000"


def test_flags_after_a_dashed_name_are_still_parsed():
    arguments = CommandLine.parse(["match.dem", "-p", "-n1clxe", "-v"])

    assert arguments.player == "-n1clxe"
    assert arguments.verbose is True


def test_verbose_before_the_demo_is_fine():
    arguments = CommandLine.parse(["-v", "match.dem", "-p", "-m0rph_"])

    assert arguments.demo == "match.dem"
    assert arguments.player == "-m0rph_"
    assert arguments.verbose is True


def test_a_real_flag_after_player_is_not_swallowed():
    with pytest.raises(SystemExit):
        CommandLine.parse(["match.dem", "-p", "-v"])


def test_normalisation_leaves_untouched_arguments_alone():
    argv = ["match.dem", "-v"]

    assert CommandLine.normalize(argv) == argv


def test_player_may_be_given_without_a_demo():
    arguments = CommandLine.parse(["-p", "-n1clxe"])

    assert arguments.demo is None
    assert arguments.player == "-n1clxe"


def build_demos(root: Path, names: list[str]) -> Path:
    folder = root / "demos"
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        (folder / name).write_bytes(b"PBDEMS2")
    return folder


def test_locator_finds_a_demo_by_file_name(tmp_path: Path):
    folder = build_demos(tmp_path, ["dust1309.dem", "other.dem"])

    found = DemoLocator([folder]).find_by_name("dust1309.dem")

    assert found is not None
    assert found.name == "dust1309.dem"


def test_locator_accepts_a_name_without_the_extension(tmp_path: Path):
    folder = build_demos(tmp_path, ["dust1309.dem"])

    assert DemoLocator([folder]).find_by_name("dust1309") is not None


def test_locator_ignores_case(tmp_path: Path):
    folder = build_demos(tmp_path, ["Dust1309.dem"])

    assert DemoLocator([folder]).find_by_name("DUST1309.DEM") is not None


def test_locator_returns_nothing_for_an_unknown_name(tmp_path: Path):
    folder = build_demos(tmp_path, ["dust1309.dem"])

    assert DemoLocator([folder]).find_by_name("missing.dem") is None


def test_locator_searches_nested_folders(tmp_path: Path):
    nested = tmp_path / "demos" / "faceit"
    nested.mkdir(parents=True)
    (nested / "deep.dem").write_bytes(b"PBDEMS2")

    assert DemoLocator([tmp_path / "demos"]).find_by_name("deep.dem") is not None


def test_search_directories_are_exposed_for_error_messages(tmp_path: Path):
    locator = DemoLocator([tmp_path / "a", tmp_path / "b"])

    assert locator.search_directories == [tmp_path / "a", tmp_path / "b"]
