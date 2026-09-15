from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from rich.console import Console

from highlighter.config.schema import ApplicationConfig, UpdateConfig
from highlighter.infrastructure.errors import DownloadError
from highlighter.infrastructure.paths import ApplicationPaths
from highlighter.provisioning.release_resolver import GithubReleaseResolver, ReleaseInfo
from highlighter.update.checker import UpdateCheck, UpdateChecker
from highlighter.update.installer import UpdateInstaller
from highlighter.update.payload import PayloadStager, UpdateError
from highlighter.update.service import UpdateService
from highlighter.update.swap import SwapScriptWriter
from highlighter.version import Version

RELEASE_EXECUTABLE = "HighlighterCS2.exe"


def quiet_console() -> Console:
    return Console(file=io.StringIO(), width=100, no_color=True)


def make_release(tag: str = "v1.3.0") -> ReleaseInfo:
    return ReleaseInfo(
        tag=tag,
        name=f"HighlighterCS2 {tag}",
        asset_name="HighlighterCS2.zip",
        asset_url="https://example.invalid/HighlighterCS2.zip",
        size_bytes=143_000_000,
        published_at="2026-09-14T10:24:14Z",
        notes="Fixed a thing\nAdded another",
        page_url="https://example.invalid/release",
    )


def test_a_plain_version_parses():
    assert Version.parse("1.2.3") == Version(1, 2, 3)


def test_a_tagged_version_parses():
    assert Version.parse("v1.2.3") == Version(1, 2, 3)
    assert Version.parse("HighlighterCS2-2.0.1") == Version(2, 0, 1)


def test_a_short_version_fills_the_missing_parts():
    assert Version.parse("2") == Version(2, 0, 0)
    assert Version.parse("2.4") == Version(2, 4, 0)


def test_a_prerelease_suffix_is_ignored():
    assert Version.parse("1.5.0-beta.2") == Version(1, 5, 0)


def test_nonsense_is_not_a_version():
    assert Version.parse("nightly") is None
    assert Version.parse("") is None


def test_versions_compare_by_number_not_by_text():
    assert Version.parse("1.10.0") > Version.parse("1.9.0")
    assert Version.parse("2.0.0").is_newer_than(Version.parse("1.99.99"))
    assert not Version.parse("1.0.0").is_newer_than(Version.parse("1.0.0"))


def test_an_update_is_offered_only_when_it_is_newer():
    current = Version(1, 2, 0)

    assert UpdateCheck(current, Version(1, 3, 0)).available is True
    assert UpdateCheck(current, Version(1, 2, 0)).available is False
    assert UpdateCheck(current, Version(1, 1, 9)).available is False


def test_an_unreadable_tag_is_reported_as_unknown():
    check = UpdateCheck(Version(1, 2, 0), None)

    assert check.is_unknown is True
    assert check.available is False


def test_a_check_serialises_for_the_launcher():
    document = UpdateCheck(Version(1, 2, 0), Version(1, 3, 0), make_release()).to_mapping()

    assert document["current"] == "1.2.0"
    assert document["latest"] == "1.3.0"
    assert document["available"] is True
    assert document["release"]["assetName"] == "HighlighterCS2.zip"


def test_the_resolver_reads_the_tag_and_the_asset(monkeypatch):
    payload = {
        "tag_name": "v1.4.0",
        "name": "Spring release",
        "published_at": "2026-09-14T10:24:14Z",
        "body": "notes",
        "html_url": "https://example.invalid/r",
        "assets": [
            {"name": "notes.txt", "browser_download_url": "u1", "size": 1},
            {"name": "HighlighterCS2.zip", "browser_download_url": "u2", "size": 42},
        ],
    }
    resolver = GithubReleaseResolver(5)
    monkeypatch.setattr(resolver, "_fetch", lambda url: payload)

    release = resolver.resolve_release("https://example.invalid/api", "*.zip")

    assert release.tag == "v1.4.0"
    assert release.asset_name == "HighlighterCS2.zip"
    assert release.asset_url == "u2"
    assert release.size_bytes == 42


def test_a_release_without_a_matching_asset_is_an_error(monkeypatch):
    resolver = GithubReleaseResolver(5)
    monkeypatch.setattr(resolver, "_fetch", lambda url: {"tag_name": "v1", "assets": []})

    with pytest.raises(DownloadError):
        resolver.resolve_release("https://example.invalid/api", "*.zip")


def test_signature_assets_are_skipped(monkeypatch):
    payload = {
        "tag_name": "v1",
        "assets": [
            {"name": "HighlighterCS2.zip.asc", "browser_download_url": "sig"},
            {"name": "HighlighterCS2.zip", "browser_download_url": "real"},
        ],
    }
    resolver = GithubReleaseResolver(5)
    monkeypatch.setattr(resolver, "_fetch", lambda url: payload)

    assert resolver.resolve_release("u", "*.zip").asset_url == "real"


def test_the_checker_compares_against_the_running_version(monkeypatch):
    checker = UpdateChecker(UpdateConfig(), Version(1, 0, 0))
    monkeypatch.setattr(checker._resolver, "resolve_release", lambda url, pattern: make_release())

    check = checker.check()

    assert check.available is True
    assert check.latest == Version(1, 3, 0)


def build_archive(destination: Path, root_folder: str = "HighlighterCS2") -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w") as bundle:
        prefix = f"{root_folder}/" if root_folder else ""
        bundle.writestr(f"{prefix}{RELEASE_EXECUTABLE}", "exe")
        bundle.writestr(f"{prefix}_internal/base_library.zip", "lib")
        bundle.writestr(f"{prefix}config.json", "{}")
        bundle.writestr(f"{prefix}README.md", "readme")
    return destination


def stage(tmp_path: Path, archive: Path) -> PayloadStager:
    stager = PayloadStager(quiet_console(), UpdateConfig(), tmp_path / "update")
    stager._download = lambda release: archive
    return stager


def test_a_release_inside_a_folder_is_found(tmp_path):
    archive = build_archive(tmp_path / "rel.zip")

    payload = stage(tmp_path, archive).stage(make_release())

    assert payload.root.name == "HighlighterCS2"
    assert payload.executable.is_file()
    assert payload.version == Version(1, 3, 0)


def test_a_release_at_the_archive_root_is_found(tmp_path):
    archive = build_archive(tmp_path / "rel.zip", root_folder="")

    payload = stage(tmp_path, archive).stage(make_release())

    assert payload.executable.is_file()


def test_an_archive_without_the_program_is_refused(tmp_path):
    archive = tmp_path / "rel.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("notes.txt", "hello")

    with pytest.raises(UpdateError, match="HighlighterCS2.exe"):
        stage(tmp_path, archive).stage(make_release())


def test_an_archive_without_the_bundle_is_refused(tmp_path):
    archive = tmp_path / "rel.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(f"HighlighterCS2/{RELEASE_EXECUTABLE}", "exe")

    with pytest.raises(UpdateError, match="_internal"):
        stage(tmp_path, archive).stage(make_release())


def test_something_that_is_not_a_zip_is_refused(tmp_path):
    archive = tmp_path / "rel.zip"
    archive.write_bytes(b"not a zip")

    with pytest.raises(UpdateError):
        stage(tmp_path, archive).stage(make_release())


def write_swap(tmp_path: Path, relaunch: bool = False) -> str:
    writer = SwapScriptWriter(tmp_path / "update", tmp_path / "logs")
    plan = writer.write(
        target=tmp_path / "release",
        payload_root=tmp_path / "update" / "staged" / "HighlighterCS2",
        archive=tmp_path / "update" / "rel.zip",
        process_id=4242,
        version="1.3.0",
        protected_files=["config.json"],
        protected_directories=["Highlighter", "demos", "tools", "work", "logs"],
        relaunch=relaunch,
    )
    return plan.script.read_text(encoding="utf-8")


def test_the_installer_waits_for_the_old_process(tmp_path):
    script = write_swap(tmp_path)

    assert ":wait" in script
    assert "goto ready" in script
    assert "4242" in script


def test_the_installer_calls_windows_tools_by_full_path(tmp_path):
    script = write_swap(tmp_path)

    for tool in ("ping.exe", "robocopy.exe"):
        assert f'"%SYSTEM%{chr(92)}{tool}"' in script
    assert r'set "SYSTEM=%SystemRoot%\System32"' in script


def test_the_installer_gives_up_rather_than_replacing_a_running_program(tmp_path):
    script = write_swap(tmp_path)

    assert ":giveup" in script
    assert "nothing changed" in script


def test_the_installer_never_touches_the_config_or_the_clips(tmp_path):
    script = write_swap(tmp_path)

    assert '/XF "config.json"' in script
    for name in ("Highlighter", "demos", "tools", "work", "logs"):
        assert f'"{name}"' in script


def test_the_installer_replaces_the_bundle_wholesale(tmp_path):
    script = write_swap(tmp_path)

    assert r'rmdir /s /q "%TARGET%\_internal"' in script
    assert "robocopy" in script


def test_the_installer_leaves_a_marker_for_the_next_start(tmp_path):
    script = write_swap(tmp_path)

    assert '>"%MARKER%" echo 1.3.0' in script


def test_the_installer_can_relaunch_when_asked(tmp_path):
    assert "start " in write_swap(tmp_path, relaunch=True)
    assert "start " not in write_swap(tmp_path, relaunch=False)


def test_writing_the_script_clears_a_stale_marker(tmp_path):
    writer = SwapScriptWriter(tmp_path / "update", tmp_path / "logs")
    (tmp_path / "update").mkdir(parents=True)
    writer.plan().marker.write_text("0.9.0", encoding="utf-8")

    write_swap(tmp_path)

    assert not writer.plan().marker.exists()


def test_the_protected_list_covers_every_runtime_folder(tmp_path):
    installer = UpdateInstaller(quiet_console(), ApplicationPaths(tmp_path), ApplicationConfig())

    assert installer._protected_files() == ["config.json"]
    assert installer._protected_directories() == [
        "Highlighter",
        "demos",
        "logs",
        "tools",
        "work",
    ]


def test_a_folder_outside_the_release_is_not_listed_as_protected(tmp_path):
    config = ApplicationConfig()
    config.paths.output_directory = r"D:\Elsewhere\Clips"
    installer = UpdateInstaller(quiet_console(), ApplicationPaths(tmp_path), config)

    assert "Clips" not in installer._protected_directories()


def test_updating_from_source_is_refused(tmp_path):
    installer = UpdateInstaller(quiet_console(), ApplicationPaths(tmp_path), ApplicationConfig())

    with pytest.raises(UpdateError, match="built release"):
        installer.install(make_release())


def test_the_next_start_announces_what_was_installed(tmp_path):
    config = ApplicationConfig()
    service = UpdateService(quiet_console(), ApplicationPaths(tmp_path), config)
    service.marker_file.parent.mkdir(parents=True, exist_ok=True)
    service.marker_file.write_text("1.3.0\n", encoding="utf-8")

    assert service.announce_installed() == "1.3.0"
    assert not service.marker_file.exists()


def test_nothing_is_announced_without_a_marker(tmp_path):
    service = UpdateService(quiet_console(), ApplicationPaths(tmp_path), ApplicationConfig())

    assert service.announce_installed() == ""


def test_the_update_flag_is_understood():
    from highlighter.cli import CommandLine

    assert CommandLine.parse(["-update"]).update is True
    assert CommandLine.parse(["--update"]).update is True
    assert CommandLine.parse(["match.dem"]).update is False


def test_the_installer_does_not_shell_out_to_tasklist(tmp_path):
    script = write_swap(tmp_path)

    assert "tasklist" not in script
    assert "find.exe" not in script


def test_the_installer_waits_on_the_program_file_itself(tmp_path):
    script = write_swap(tmp_path)

    assert r'2>nul (>>"%TARGET%\HighlighterCS2.exe" (call )) && goto ready' in script


def test_the_installer_still_gives_up_rather_than_forcing_it(tmp_path):
    script = write_swap(tmp_path)

    assert ":giveup" in script
    assert script.index(":giveup") < script.index(":ready")


def test_a_truncated_download_is_refused(tmp_path):
    from highlighter.provisioning.downloader import FileDownloader

    destination = tmp_path / "release.zip"
    destination.write_bytes(b"0" * 100)
    downloader = FileDownloader(quiet_console(), 5)

    with pytest.raises(DownloadError, match="incomplete"):
        downloader._verify(destination, "release.zip", 100, 5_000, 0)

    assert not destination.exists()


def test_a_download_that_matches_the_announced_size_is_accepted(tmp_path):
    from highlighter.provisioning.downloader import FileDownloader

    destination = tmp_path / "release.zip"
    destination.write_bytes(b"0" * 100)

    FileDownloader(quiet_console(), 5)._verify(destination, "release.zip", 100, 100, 0)

    assert destination.is_file()


def test_the_release_size_is_used_when_the_server_announces_nothing(tmp_path):
    from highlighter.provisioning.downloader import FileDownloader

    destination = tmp_path / "release.zip"
    destination.write_bytes(b"0" * 100)
    downloader = FileDownloader(quiet_console(), 5)

    with pytest.raises(DownloadError, match="incomplete"):
        downloader._verify(destination, "release.zip", 100, None, 143_132_983)


def test_an_empty_download_is_refused(tmp_path):
    from highlighter.provisioning.downloader import FileDownloader

    destination = tmp_path / "release.zip"
    destination.write_bytes(b"")

    with pytest.raises(DownloadError, match="empty"):
        FileDownloader(quiet_console(), 5)._verify(destination, "release.zip", 0, 0, 0)


def test_the_release_size_reaches_the_downloader(tmp_path, monkeypatch):
    from highlighter.update.payload import PayloadStager

    seen = {}
    stager = PayloadStager(quiet_console(), UpdateConfig(), tmp_path / "update")

    class Recorder:
        def __init__(self, console, timeout):
            pass

        def download(self, url, destination, label, expected_bytes=0):
            seen["expected"] = expected_bytes
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"x")
            return destination

    monkeypatch.setattr("highlighter.update.payload.FileDownloader", Recorder)
    stager._download(make_release())

    assert seen["expected"] == 143_000_000
