from __future__ import annotations

import io
from pathlib import Path

from rich.console import Console

from highlighter.config.schema import PathsConfig, ToolchainConfig
from highlighter.infrastructure.paths import ApplicationPaths
from highlighter.presentation.theme import HIGHLIGHTER_THEME
from highlighter.tooling.check import ToolCheck, ToolchainInspector, ToolState
from highlighter.tooling.inventory import ToolInventory, ToolStatus
from highlighter.tooling.latest import LatestVersion, LatestVersionResolver
from highlighter.tooling.probe import FileVersionReader, ProcessVersionReader
from highlighter.tooling.report import ToolsView

HOOK_DLL = "x64/AfxHookSource2.dll"
INJECTOR_FILES = ("AfxHook.dat", "injector.exe")


def make_hlae(root: Path, complete: bool = True) -> Path:
    install = root / "hlae"
    injector = install / "x64"
    injector.mkdir(parents=True, exist_ok=True)
    executable = install / "HLAE.exe"
    executable.write_bytes(b"MZ")
    if complete:
        for name in (*INJECTOR_FILES, "AfxHookSource2.dll"):
            (injector / name).write_bytes(b"MZ")
    return executable


def make_ffmpeg(root: Path) -> Path:
    folder = root / "ffmpeg" / "ffmpeg-9.0.2-essentials_build" / "bin"
    folder.mkdir(parents=True, exist_ok=True)
    executable = folder / "ffmpeg.exe"
    executable.write_bytes(b"MZ")
    return executable


def build_inventory(tools: Path, paths: PathsConfig | None = None) -> ToolInventory:
    return ToolInventory(
        paths=paths or PathsConfig(),
        tools_directory=tools,
        hook_dll_relative_path=HOOK_DLL,
        application_paths=ApplicationPaths(tools.parent),
    )


def status(**fields) -> ToolStatus:
    base = {"key": "hlae", "label": "HLAE"}
    return ToolStatus(**{**base, **fields})


def render(checks) -> str:
    console = Console(file=io.StringIO(), width=100, theme=HIGHLIGHTER_THEME, no_color=True)
    ToolsView(console).render(checks)
    return console.file.getvalue()


def test_a_four_part_file_version_loses_its_trailing_zero():
    assert FileVersionReader._render(2 << 16 | 192, 3 << 16 | 0) == "2.192.3"


def test_a_file_version_keeps_three_parts():
    assert FileVersionReader._render(1 << 16 | 0, 0) == "1.0.0"


def test_a_revision_is_kept_when_it_is_not_zero():
    assert FileVersionReader._render(2 << 16 | 1, 3 << 16 | 4) == "2.1.3.4"


def test_the_version_line_of_ffmpeg_is_read():
    output = "ffmpeg version 9.0.2-essentials_build-www.gyan.dev Copyright (c) 2000"

    assert ProcessVersionReader._first_version(output) == "9.0.2-essentials_build-www.gyan.dev"


def test_a_line_without_a_version_gives_nothing():
    assert ProcessVersionReader._first_version("nothing here") == ""


def test_no_output_gives_nothing():
    assert ProcessVersionReader._first_version("") == ""


def test_an_absent_tool_reports_itself_as_missing(tmp_path: Path):
    found = build_inventory(tmp_path / "tools").hlae()

    assert found.is_installed is False
    assert found.source == ""
    assert found.version is None


def test_a_tool_in_the_tools_folder_is_found(tmp_path: Path):
    tools = tmp_path / "tools"
    executable = make_hlae(tools)

    found = build_inventory(tools).hlae()

    assert found.executable == executable
    assert found.source == "tools folder"
    assert found.is_managed is True
    assert found.managed_root == tools / "hlae"


def test_an_incomplete_install_lists_what_is_gone(tmp_path: Path):
    tools = tmp_path / "tools"
    make_hlae(tools, complete=False)

    found = build_inventory(tools).hlae()

    assert found.is_complete is False
    assert "injector.exe" in found.missing_names


def test_a_configured_path_wins(tmp_path: Path):
    tools = tmp_path / "tools"
    make_hlae(tools)
    elsewhere = tmp_path / "own" / "HLAE.exe"
    elsewhere.parent.mkdir(parents=True)
    elsewhere.write_bytes(b"MZ")

    found = build_inventory(tools, PathsConfig(hlae_executable=str(elsewhere))).hlae()

    assert found.executable == elsewhere
    assert found.source == "config.json"
    assert found.is_managed is False


def test_a_configured_path_that_is_gone_reads_as_missing(tmp_path: Path):
    found = build_inventory(
        tmp_path / "tools", PathsConfig(hlae_executable=str(tmp_path / "nope.exe"))
    ).hlae()

    assert found.is_installed is False


def test_ffmpeg_is_found_deep_inside_its_archive(tmp_path: Path):
    tools = tmp_path / "tools"
    executable = make_ffmpeg(tools)

    found = build_inventory(tools).ffmpeg()

    assert found.executable == executable
    assert found.managed_root == tools / "ffmpeg"


def test_a_version_is_shown_without_its_build_flavour():
    assert status(version_text="9.0.2-essentials_build-www.gyan.dev").shown_version == "9.0.2"


def test_a_version_that_cannot_be_read_is_shown_as_it_came():
    assert status(version_text="mystery").shown_version == "mystery"


def test_a_tag_is_shown_without_its_letter():
    assert LatestVersion(text="v2.192.3").shown == "2.192.3"


def test_a_newest_version_that_failed_is_not_known():
    assert LatestVersion(error="offline").is_known is False


def test_a_tool_without_a_source_says_so():
    resolver = LatestVersionResolver(ToolchainConfig(ffmpeg_version_url=""))

    assert resolver.ffmpeg().error != ""


def test_an_unknown_tool_has_no_source():
    assert LatestVersionResolver(ToolchainConfig()).for_tool("nothing").is_known is False


def test_a_missing_tool_is_reported_as_missing():
    assert ToolCheck(status=status()).state is ToolState.MISSING


def test_a_damaged_tool_is_reported_before_its_version():
    check = ToolCheck(
        status=status(executable=Path("HLAE.exe"), missing_files=(Path("injector.exe"),)),
        latest=LatestVersion(text="2.192.3"),
    )

    assert check.state is ToolState.DAMAGED


def test_an_older_install_is_reported_as_outdated():
    check = ToolCheck(
        status=status(executable=Path("HLAE.exe"), version_text="2.192.2"),
        latest=LatestVersion(text="v2.192.3"),
    )

    assert check.state is ToolState.OUTDATED
    assert check.needs_attention is True


def test_the_same_version_is_up_to_date():
    check = ToolCheck(
        status=status(executable=Path("HLAE.exe"), version_text="2.192.3"),
        latest=LatestVersion(text="v2.192.3"),
    )

    assert check.state is ToolState.CURRENT
    assert check.needs_attention is False


def test_a_newer_install_than_the_source_is_not_an_error():
    check = ToolCheck(
        status=status(executable=Path("HLAE.exe"), version_text="3.0.0"),
        latest=LatestVersion(text="v2.192.3"),
    )

    assert check.state is ToolState.NEWER
    assert check.needs_attention is False


def test_nothing_to_compare_against_is_admitted():
    check = ToolCheck(
        status=status(executable=Path("HLAE.exe"), version_text="2.192.3"),
        latest=LatestVersion(error="offline"),
    )

    assert check.state is ToolState.UNKNOWN


def test_an_unreadable_installed_version_is_admitted():
    check = ToolCheck(
        status=status(executable=Path("HLAE.exe")),
        latest=LatestVersion(text="v2.192.3"),
    )

    assert check.state is ToolState.UNKNOWN


def test_the_inspector_can_be_asked_to_stay_offline(tmp_path: Path):
    tools = tmp_path / "tools"
    make_hlae(tools)
    inspector = ToolchainInspector(
        paths=PathsConfig(),
        settings=ToolchainConfig(),
        tools_directory=tools,
        hook_dll_relative_path=HOOK_DLL,
        application_paths=ApplicationPaths(tmp_path),
    )

    checks = inspector.inspect(ask_online=False)

    assert len(checks) == 2
    assert all(check.latest.text == "" for check in checks)


def test_the_report_names_both_tools_and_their_state():
    checks = (
        ToolCheck(
            status=status(executable=Path("HLAE.exe"), version_text="2.192.2", source="tools folder", managed_root=Path("tools/hlae")),
            latest=LatestVersion(text="v2.192.3"),
        ),
        ToolCheck(
            status=ToolStatus(key="ffmpeg", label="ffmpeg", executable=Path("ffmpeg.exe"), version_text="9.0.2", source="on PATH"),
            latest=LatestVersion(text="9.0.2"),
        ),
    )

    shown = render(checks)

    assert "HLAE" in shown
    assert "ffmpeg" in shown
    assert "a newer one is out" in shown
    assert "up to date" in shown


def test_the_report_says_how_to_replace_a_managed_tool():
    check = ToolCheck(
        status=status(
            executable=Path("HLAE.exe"),
            version_text="2.192.2",
            source="tools folder",
            managed_root=Path("tools/hlae"),
        ),
        latest=LatestVersion(text="v2.192.3"),
    )

    assert "downloads itself" in render((check,))


def test_the_report_leaves_a_tool_it_does_not_manage_alone():
    check = ToolCheck(
        status=status(executable=Path("HLAE.exe"), version_text="2.192.2", source="on PATH"),
        latest=LatestVersion(text="v2.192.3"),
    )

    assert "not managed here" in render((check,))


def test_the_report_explains_a_failed_check():
    check = ToolCheck(
        status=status(executable=Path("HLAE.exe"), version_text="2.192.3"),
        latest=LatestVersion(error="could not reach github"),
    )

    assert "could not reach github" in render((check,))
