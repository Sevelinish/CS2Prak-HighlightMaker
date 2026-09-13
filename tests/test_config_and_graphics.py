from __future__ import annotations

import json
from pathlib import Path

import pytest

from highlighter.config.migrations import CURRENT_VERSION
from highlighter.config.repository import ConfigRepository
from highlighter.config.schema import ApplicationConfig, GameConfig, RecordingConfig
from highlighter.game.installation import Cs2Installation
from highlighter.infrastructure.errors import ConfigurationError
from highlighter.recording.graphics import GraphicsProfile

SAMPLE_VIDEO_SETTINGS = """"video.cfg"
{
\t"Version"\t\t"16"
\t"VendorID"\t\t"4318"
\t"setting.cpu_level"\t\t"0"
\t"setting.defaultres"\t\t"1280"
\t"setting.defaultresheight"\t\t"1024"
\t"setting.fullscreen"\t\t"1"
\t"Autoconfig"\t\t"2"
\t"setting.msaa_samples"\t\t"0"
}
"""


def test_missing_config_is_created_with_defaults(tmp_path: Path):
    config_file = tmp_path / "config.json"
    config = ConfigRepository(config_file).load()

    assert config_file.is_file()
    assert config.recording.width == 1920
    assert config.recording.height == 1080
    assert config.recording.fps == 60


def test_partial_config_keeps_user_values_and_backfills(tmp_path: Path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"recording": {"fps": 120}}), encoding="utf-8")

    config = ConfigRepository(config_file).load()

    assert config.recording.fps == 120
    assert config.recording.width == 1920
    assert "toolchain" in json.loads(config_file.read_text(encoding="utf-8"))


def test_broken_json_raises_configuration_error(tmp_path: Path):
    config_file = tmp_path / "config.json"
    config_file.write_text("{ not json", encoding="utf-8")

    with pytest.raises(ConfigurationError):
        ConfigRepository(config_file).load()


def test_config_round_trips_without_loss():
    original = ApplicationConfig()
    restored = ApplicationConfig.from_mapping(original.to_mapping())

    assert restored.to_mapping() == original.to_mapping()


def test_custom_tag_weight_overrides_default(tmp_path: Path):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"detection": {"tagWeights": {"kills_5": 999.0}}}), encoding="utf-8"
    )

    config = ConfigRepository(config_file).load()

    assert config.detection.weight_of("kills_5") == 999.0
    assert config.detection.weight_of("kills_3") == 12.0


class StubInstallation(Cs2Installation):
    def __init__(self, settings_file: Path) -> None:
        self._settings_file = settings_file

    def video_settings_files(self) -> list[Path]:
        return [self._settings_file]


def test_graphics_profile_upgrades_existing_keys(tmp_path: Path):
    settings_file = tmp_path / "cs2_video.txt"
    settings_file.write_text(SAMPLE_VIDEO_SETTINGS, encoding="utf-8")

    profile = GraphicsProfile(
        StubInstallation(settings_file), RecordingConfig(), GameConfig()
    )
    profile.apply()
    content = settings_file.read_text(encoding="utf-8")

    assert '"setting.defaultres"\t\t"1920"' in content
    assert '"setting.defaultresheight"\t\t"1080"' in content
    assert '"setting.fullscreen"\t\t"0"' in content
    assert '"setting.msaa_samples"\t\t"8"' in content
    assert '"Autoconfig"\t\t"0"' in content
    assert '"VendorID"\t\t"4318"' in content


def test_graphics_profile_does_not_invent_unknown_keys(tmp_path: Path):
    settings_file = tmp_path / "cs2_video.txt"
    settings_file.write_text(SAMPLE_VIDEO_SETTINGS, encoding="utf-8")

    GraphicsProfile(StubInstallation(settings_file), RecordingConfig(), GameConfig()).apply()

    assert "videocfg_shadow_quality" not in settings_file.read_text(encoding="utf-8")


def test_graphics_profile_restores_original_file(tmp_path: Path):
    settings_file = tmp_path / "cs2_video.txt"
    settings_file.write_text(SAMPLE_VIDEO_SETTINGS, encoding="utf-8")

    profile = GraphicsProfile(StubInstallation(settings_file), RecordingConfig(), GameConfig())
    profile.apply()
    profile.restore()

    assert settings_file.read_text(encoding="utf-8") == SAMPLE_VIDEO_SETTINGS
    assert not list(tmp_path.glob("*.highlighter-backup"))


BROKEN_V1_CONFIG = {
    "game": {
        "tickRate": 64,
        "launchArguments": ["-insecure", "-novid", "-console", "-allow_third_party_software"],
        "hlaeArgumentTemplate": [
            "-csgoLauncher",
            "-noGui",
            "-autoStart",
            "-customLoader",
            "-csgoExe",
            "{game_executable}",
            "-gameArgs",
            "{game_arguments}",
        ],
    },
    "recording": {"fps": 120},
}


def test_version_one_config_is_migrated_to_the_custom_loader(tmp_path: Path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(BROKEN_V1_CONFIG), encoding="utf-8")

    config = ConfigRepository(config_file).load()

    assert "-csgoLauncher" not in config.game.hlae_argument_template
    assert "-programPath" in config.game.hlae_argument_template
    assert "-hookDllPath" in config.game.hlae_argument_template
    assert "-steam" in config.game.launch_arguments
    assert "-afxDisableSteamStorage" in config.game.launch_arguments
    assert config.game.hook_dll_relative_path == "x64/AfxHookSource2.dll"
    assert config.game.steam_environment["SteamAppId"] == "730"


def test_migration_preserves_unrelated_user_values(tmp_path: Path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(BROKEN_V1_CONFIG), encoding="utf-8")

    config = ConfigRepository(config_file).load()

    assert config.recording.fps == 120
    assert config.game.tick_rate == 64


def test_upgrading_from_every_earlier_version_stays_consistent(tmp_path: Path):
    for version in (1, 2, 3, 4):
        config_file = tmp_path / f"config_v{version}.json"
        config_file.write_text(
            json.dumps({"version": version, "recording": {"fps": 111}}), encoding="utf-8"
        )

        config = ConfigRepository(config_file).load()

        assert config.recording.fps == 111
        assert config.recording.capture_mode == "crosshair"
        assert config.crosshair.enabled is False
        assert any(
            command.startswith("spec_player") for command in config.recording.spectate_commands
        )
        assert config.game.console_variables["cl_trueview_show_status"] == "0"
        assert config.game.console_variables["spec_autodirector"] == "0"
        assert json.loads(config_file.read_text(encoding="utf-8"))["version"] == CURRENT_VERSION


def test_version_two_config_gains_the_cs2_clip_settings(tmp_path: Path):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "version": 2,
                "recording": {
                    "fps": 120,
                    "preRollSeconds": 4.0,
                    "spectateCommandTemplate": "spec_player_by_accountid {account_id}",
                },
                "encoding": {"crf": 18},
                "game": {"consoleVariables": {"volume": "0.9"}},
            }
        ),
        encoding="utf-8",
    )

    config = ConfigRepository(config_file).load()

    assert any(
        command.startswith("spec_player") for command in config.recording.spectate_commands
    )
    assert config.recording.lead_in_seconds == 2.0
    assert config.recording.gap_hold_seconds == 4.0
    assert config.game.console_variables["spec_show_xray"] == "0"
    assert config.game.console_variables["demo_ui_mode"] == "0"
    assert config.game.console_variables["volume"] == "0.9"
    assert config.encoding.quality == 18
    assert config.encoding.video_codec == "auto"
    assert config.recording.fps == 120


def test_migration_stamps_the_version_on_disk(tmp_path: Path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(BROKEN_V1_CONFIG), encoding="utf-8")

    ConfigRepository(config_file).load()
    stored = json.loads(config_file.read_text(encoding="utf-8"))

    assert stored["version"] == CURRENT_VERSION


def test_current_config_is_not_migrated_again(tmp_path: Path):
    config_file = tmp_path / "config.json"
    ConfigRepository(config_file).load()
    first = config_file.read_text(encoding="utf-8")

    ConfigRepository(config_file).load()

    assert config_file.read_text(encoding="utf-8") == first


def test_editing_one_console_variable_keeps_the_rest(tmp_path: Path):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "version": CURRENT_VERSION,
                "game": {"consoleVariables": {"volume": "0.1"}},
            }
        ),
        encoding="utf-8",
    )

    config = ConfigRepository(config_file).load()

    assert config.game.console_variables["volume"] == "0.1"
    assert config.game.console_variables["spec_autodirector"] == "0"
    assert config.game.console_variables["demo_ui_mode"] == "0"
    assert config.game.console_variables["spec_show_xray"] == "0"


def test_editing_one_steam_variable_keeps_the_rest(tmp_path: Path):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "version": CURRENT_VERSION,
                "game": {"steamEnvironment": {"SteamClientLaunch": "0"}},
            }
        ),
        encoding="utf-8",
    )

    config = ConfigRepository(config_file).load()

    assert config.game.steam_environment["SteamClientLaunch"] == "0"
    assert config.game.steam_environment["SteamAppId"] == "730"
