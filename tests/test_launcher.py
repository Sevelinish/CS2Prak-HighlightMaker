from __future__ import annotations

from pathlib import Path

import pytest

from highlighter.config.schema import GameConfig, RecordingConfig
from highlighter.game.installation import Cs2Installation
from highlighter.infrastructure.errors import RecordingError, ToolchainError
from highlighter.provisioning.hlae_installation import HlaeInstallation
from highlighter.recording.launcher import HlaeLauncher

DEMO = Path(r"D:\demos\a match.dem")
STEAM_ROOT = Path(r"C:\Program Files (x86)\Steam")


class StubCs2Installation(Cs2Installation):
    def __init__(self, root: Path) -> None:
        self._root = root
        self._steam = None


@pytest.fixture
def hlae(tmp_path: Path) -> HlaeInstallation:
    root = tmp_path / "hlae"
    (root / "x64").mkdir(parents=True)
    (root / "x64" / "AfxHookSource2.dll").write_bytes(b"hook")
    executable = root / "HLAE.exe"
    executable.write_bytes(b"exe")
    return HlaeInstallation(executable, GameConfig().hook_dll_relative_path)


@pytest.fixture
def game_installation(tmp_path: Path) -> Cs2Installation:
    return StubCs2Installation(tmp_path / "Counter-Strike Global Offensive")


def build_launcher(hlae, game_installation, recording=None, game=None) -> HlaeLauncher:
    return HlaeLauncher(
        hlae=hlae,
        installation=game_installation,
        recording=recording or RecordingConfig(),
        game=game or GameConfig(),
        steam_root=STEAM_ROOT,
    )


def test_uses_the_custom_loader_not_the_csgo_launcher(hlae, game_installation):
    arguments = build_launcher(hlae, game_installation).build_arguments("session", DEMO)

    assert "-customLoader" in arguments
    assert "-programPath" in arguments
    assert "-cmdLine" in arguments
    assert "-hookDllPath" in arguments
    assert "-csgoLauncher" not in arguments
    assert "-csgoExe" not in arguments


def test_injects_the_64_bit_cs2_hook(hlae, game_installation):
    arguments = build_launcher(hlae, game_installation).build_arguments("session", DEMO)
    hook = arguments[arguments.index("-hookDllPath") + 1]

    assert hook.endswith(str(Path("x64") / "AfxHookSource2.dll"))
    assert Path(hook).is_file()


def test_program_path_points_at_cs2_executable(hlae, game_installation):
    arguments = build_launcher(hlae, game_installation).build_arguments("session", DEMO)
    program = arguments[arguments.index("-programPath") + 1]

    assert program.endswith("cs2.exe")


def test_command_line_carries_demo_script_and_resolution(hlae, game_installation):
    arguments = build_launcher(hlae, game_installation).build_arguments("session", DEMO)
    command_line = arguments[arguments.index("-cmdLine") + 1]

    assert "-steam" in command_line
    assert "-insecure" in command_line
    assert "-afxDisableSteamStorage" in command_line
    assert "-w 1920 -h 1080" in command_line
    assert "+exec session" in command_line
    assert f'"{DEMO}"' in command_line


def test_windowed_and_fullscreen_use_the_hlae_flags(hlae, game_installation):
    windowed = build_launcher(hlae, game_installation).build_arguments("session", DEMO)
    fullscreen = build_launcher(
        hlae, game_installation, RecordingConfig(fullscreen=True)
    ).build_arguments("session", DEMO)

    assert "-sw" in windowed[windowed.index("-cmdLine") + 1]
    assert "-full" in fullscreen[fullscreen.index("-cmdLine") + 1]


def test_environment_declares_the_steam_app(hlae, game_installation):
    environment = build_launcher(hlae, game_installation).build_environment()

    assert environment["SteamAppId"] == "730"
    assert environment["SteamGameId"] == "730"
    assert environment["SteamOverlayGameId"] == "730"
    assert environment["SteamClientLaunch"] == "1"
    assert environment["SteamPath"] == str(STEAM_ROOT)


def test_environment_keeps_inherited_variables(hlae, game_installation):
    environment = build_launcher(hlae, game_installation).build_environment()

    assert "PATH" in environment


def test_missing_hook_library_is_reported(tmp_path: Path):
    executable = tmp_path / "hlae" / "HLAE.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"exe")

    with pytest.raises(ToolchainError, match="AfxHookSource2.dll"):
        _ = HlaeInstallation(executable, "x64/AfxHookSource2.dll").hook_dll


def test_ffmpeg_is_registered_through_the_ini_file(hlae, tmp_path: Path):
    ffmpeg = tmp_path / "ffmpeg" / "bin" / "ffmpeg.exe"
    ffmpeg.parent.mkdir(parents=True)
    ffmpeg.write_bytes(b"ffmpeg")

    config_file = hlae.register_ffmpeg(ffmpeg)
    content = config_file.read_text(encoding="utf-8")

    assert config_file == hlae.root / "ffmpeg" / "ffmpeg.ini"
    assert "[Ffmpeg]" in content
    assert f"Path={ffmpeg}" in content


def test_non_ascii_install_path_is_rejected(tmp_path: Path):
    root = tmp_path / "хайлайты"
    root.mkdir()
    executable = root / "HLAE.exe"
    executable.write_bytes(b"exe")

    with pytest.raises(ToolchainError, match="non-ASCII"):
        HlaeInstallation(executable, "x64/AfxHookSource2.dll").verify_path_is_ascii()


class FakeWatcher:
    def __init__(self, running_before: bool = False, starts: bool = True, stops: bool = True):
        self.executable_name = "cs2.exe"
        self._running_before = running_before
        self._starts = starts
        self._stops = stops
        self.terminated = False
        self.progress_calls = 0

    def is_running(self) -> bool:
        return self._running_before

    def wait_until_started(self, timeout_seconds: float) -> bool:
        return self._starts

    def wait_until_stopped(self, timeout_seconds: float, on_poll=None) -> bool:
        if on_poll is not None:
            on_poll(1.0)
            self.progress_calls += 1
        return self._stops

    def terminate(self) -> None:
        self.terminated = True


def build_watched_launcher(hlae, game_installation, watcher) -> HlaeLauncher:
    return HlaeLauncher(
        hlae=hlae,
        installation=game_installation,
        recording=RecordingConfig(),
        game=GameConfig(),
        steam_root=STEAM_ROOT,
        watcher=watcher,
    )


def test_refuses_to_start_when_the_game_is_already_running(hlae, game_installation):
    launcher = build_watched_launcher(hlae, game_installation, FakeWatcher(running_before=True))

    with pytest.raises(RecordingError, match="already running"):
        launcher.run("session", DEMO)


def test_waits_for_the_game_not_for_the_loader(hlae, game_installation, monkeypatch):
    watcher = FakeWatcher()
    launcher = build_watched_launcher(hlae, game_installation, watcher)
    monkeypatch.setattr(launcher, "_inject", lambda *_: None)

    launcher.run("session", DEMO, on_progress=lambda elapsed: None)

    assert watcher.progress_calls == 1
    assert watcher.terminated is False


def test_reports_when_the_game_never_appears(hlae, game_installation, monkeypatch):
    launcher = build_watched_launcher(hlae, game_installation, FakeWatcher(starts=False))
    monkeypatch.setattr(launcher, "_inject", lambda *_: None)

    with pytest.raises(RecordingError, match="did not start"):
        launcher.run("session", DEMO)


def test_terminates_the_game_when_recording_overruns(hlae, game_installation, monkeypatch):
    watcher = FakeWatcher(stops=False)
    launcher = build_watched_launcher(hlae, game_installation, watcher)
    monkeypatch.setattr(launcher, "_inject", lambda *_: None)

    with pytest.raises(RecordingError, match="exceeded"):
        launcher.run("session", DEMO)

    assert watcher.terminated is True
