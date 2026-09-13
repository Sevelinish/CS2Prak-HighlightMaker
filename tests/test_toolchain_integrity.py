from __future__ import annotations

from pathlib import Path

import pytest
from rich.console import Console

from highlighter.config.schema import GameConfig, PathsConfig, ToolchainConfig
from highlighter.infrastructure.errors import ToolchainError
from highlighter.provisioning.hlae_installation import HlaeInstallation
from highlighter.provisioning.toolchain import (
    HLAE_EXECUTABLE,
    ToolchainProvisioner,
    ToolSpecification,
)

HOOK_RELATIVE_PATH = GameConfig().hook_dll_relative_path


def make_hlae(root: Path, complete: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "x64").mkdir(parents=True, exist_ok=True)
    executable = root / "HLAE.exe"
    executable.write_bytes(b"exe")
    (root / "x64" / "AfxHookSource2.dll").write_bytes(b"hook")
    if complete:
        (root / "x64" / "AfxHook.dat").write_bytes(b"dat")
        (root / "x64" / "injector.exe").write_bytes(b"inj")
    return executable


def test_complete_install_passes_verification(tmp_path: Path):
    installation = HlaeInstallation(make_hlae(tmp_path / "hlae"), HOOK_RELATIVE_PATH)

    assert installation.is_complete()
    assert installation.missing_files() == []
    installation.verify()


def test_install_without_afxhook_dat_is_incomplete(tmp_path: Path):
    installation = HlaeInstallation(
        make_hlae(tmp_path / "hlae", complete=False), HOOK_RELATIVE_PATH
    )

    missing = {path.name for path in installation.missing_files()}

    assert missing == {"AfxHook.dat", "injector.exe"}
    assert installation.is_complete() is False


def test_verification_error_names_the_missing_files(tmp_path: Path):
    installation = HlaeInstallation(
        make_hlae(tmp_path / "hlae", complete=False), HOOK_RELATIVE_PATH
    )

    with pytest.raises(ToolchainError, match="AfxHook.dat"):
        installation.verify()


def test_companions_are_looked_for_next_to_the_hook_library(tmp_path: Path):
    root = tmp_path / "hlae"
    make_hlae(root)
    (root / "AfxHook.dat").unlink(missing_ok=True)
    installation = HlaeInstallation(root / "HLAE.exe", HOOK_RELATIVE_PATH)

    required = {str(path.relative_to(root)) for path in installation.required_files()}

    assert str(Path("x64") / "AfxHook.dat") in required
    assert str(Path("x64") / "injector.exe") in required


def test_damaged_install_is_wiped_and_reinstalled(tmp_path: Path, monkeypatch):
    tools = tmp_path / "tools"
    damaged = tools / "hlae"
    make_hlae(damaged, complete=False)

    provisioner = build_provisioner(tools)
    reinstalls: list[Path] = []

    def fake_install(specification, install_root: Path) -> Path:
        reinstalls.append(install_root)
        return make_hlae(install_root)

    monkeypatch.setattr(provisioner, "_install", fake_install)
    resolved = provisioner._resolve(hlae_specification(provisioner), "")

    assert reinstalls == [damaged]
    assert HlaeInstallation(resolved, HOOK_RELATIVE_PATH).is_complete()


def test_complete_install_is_reused_without_downloading(tmp_path: Path, monkeypatch):
    tools = tmp_path / "tools"
    make_hlae(tools / "hlae")

    provisioner = build_provisioner(tools)
    monkeypatch.setattr(
        provisioner,
        "_install",
        lambda *_: pytest.fail("a complete install must not be downloaded again"),
    )

    resolved = provisioner._resolve(hlae_specification(provisioner), "")

    assert resolved == tools / "hlae" / "HLAE.exe"


def test_configured_but_damaged_install_is_reported_not_silently_replaced(tmp_path: Path):
    executable = make_hlae(tmp_path / "custom", complete=False)
    provisioner = build_provisioner(tmp_path / "tools")

    with pytest.raises(ToolchainError, match="incomplete"):
        provisioner._resolve(hlae_specification(provisioner), str(executable))


def build_provisioner(tools_directory: Path) -> ToolchainProvisioner:
    return ToolchainProvisioner(
        Console(),
        PathsConfig(),
        ToolchainConfig(),
        tools_directory,
        HOOK_RELATIVE_PATH,
    )


def hlae_specification(provisioner: ToolchainProvisioner) -> ToolSpecification:
    return ToolSpecification(
        key="hlae",
        label="HLAE",
        executable_name=HLAE_EXECUTABLE,
        install_folder="hlae",
        validate=provisioner._missing_hlae_files,
    )


def test_encoder_selection_prefers_hardware_when_available(tmp_path: Path, monkeypatch):
    from highlighter.config.schema import EncodingConfig
    from highlighter.media.encoders import EncoderSelector

    selector = EncoderSelector(tmp_path / "ffmpeg.exe", EncodingConfig())
    monkeypatch.setattr(selector, "_can_encode", lambda codec: codec == "h264_nvenc")

    profile = selector.select()

    assert profile.codec == "h264_nvenc"
    assert profile.is_hardware is True
    assert "-cq" in profile.output_arguments()


def test_encoder_selection_falls_back_to_software(tmp_path: Path, monkeypatch):
    from highlighter.config.schema import EncodingConfig
    from highlighter.media.encoders import EncoderSelector

    selector = EncoderSelector(tmp_path / "ffmpeg.exe", EncodingConfig())
    monkeypatch.setattr(selector, "_can_encode", lambda codec: codec == "libx264")

    profile = selector.select()

    assert profile.codec == "libx264"
    assert profile.is_hardware is False
    assert "-crf" in profile.output_arguments()


def test_explicit_codec_overrides_the_preference_list(tmp_path: Path, monkeypatch):
    from highlighter.config.schema import EncodingConfig
    from highlighter.media.encoders import EncoderSelector

    selector = EncoderSelector(tmp_path / "ffmpeg.exe", EncodingConfig(video_codec="libx264"))
    monkeypatch.setattr(selector, "_can_encode", lambda codec: True)

    assert selector.select().codec == "libx264"


def test_unusable_hardware_encoder_is_skipped(tmp_path: Path, monkeypatch):
    from highlighter.config.schema import EncodingConfig
    from highlighter.media.encoders import EncoderSelector

    selector = EncoderSelector(tmp_path / "ffmpeg.exe", EncodingConfig())
    monkeypatch.setattr(selector, "_can_encode", lambda codec: codec in {"h264_qsv", "libx264"})

    assert selector.select().codec == "h264_qsv"
