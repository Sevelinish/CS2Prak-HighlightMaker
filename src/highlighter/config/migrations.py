from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from ..infrastructure.logging import get_logger

VERSION_KEY = "version"
INITIAL_VERSION = 1


class ConfigMigration(ABC):
    version: ClassVar[int]
    reason: ClassVar[str]

    @abstractmethod
    def apply(self, raw: dict[str, Any]) -> None:
        raise NotImplementedError

    @staticmethod
    def console_variables(raw: dict[str, Any]) -> dict[str, Any]:
        game = raw.setdefault("game", {})
        variables = dict(game.get("consoleVariables") or {})
        game["consoleVariables"] = variables
        return variables


class Cs2CustomLoaderMigration(ConfigMigration):
    version = 2
    reason = (
        "HLAE has no command line launcher for CS2, so the game is now started "
        "through its custom loader"
    )
    ARGUMENT_TEMPLATE = [
        "-noGui",
        "-autoStart",
        "-customLoader",
        "-programPath",
        "{game_executable}",
        "-cmdLine",
        "{game_arguments}",
        "-hookDllPath",
        "{hook_dll}",
    ]
    LAUNCH_ARGUMENTS = [
        "-steam",
        "-insecure",
        "-afxDisableSteamStorage",
        "-novid",
        "-console",
    ]
    STEAM_ENVIRONMENT = {
        "SteamAppId": "730",
        "SteamGameId": "730",
        "SteamOverlayGameId": "730",
        "SteamClientLaunch": "1",
    }

    def apply(self, raw: dict[str, Any]) -> None:
        game = raw.setdefault("game", {})
        game["hlaeArgumentTemplate"] = list(self.ARGUMENT_TEMPLATE)
        game["launchArguments"] = list(self.LAUNCH_ARGUMENTS)
        game.setdefault("hookDllRelativePath", "x64/AfxHookSource2.dll")
        game.setdefault("steamEnvironment", dict(self.STEAM_ENVIRONMENT))


class Cs2ClipQualityMigration(ConfigMigration):
    version = 3
    reason = (
        "CS2 needs its own spectator and demo-UI cvars, and clips are now cut "
        "into segments that skip dead time"
    )
    SEGMENT_DEFAULTS = {
        "leadInSeconds": 2.0,
        "resumeLeadSeconds": 1.5,
        "gapHoldSeconds": 4.0,
    }
    REQUIRED_VARIABLES = {
        "demo_ui_mode": "0",
        "spec_show_xray": "0",
        "snd_mute_losefocus": "0",
        "spec_autodirector": "0",
    }
    PREFERRED_CODECS = ["h264_nvenc", "h264_amf", "h264_qsv", "libx264"]
    DEFAULT_QUALITY = 20

    def apply(self, raw: dict[str, Any]) -> None:
        recording = raw.setdefault("recording", {})
        recording.pop("preRollSeconds", None)
        for key, value in self.SEGMENT_DEFAULTS.items():
            recording.setdefault(key, value)

        self.console_variables(raw).update(self.REQUIRED_VARIABLES)

        encoding = raw.setdefault("encoding", {})
        legacy_quality = encoding.pop("crf", None)
        encoding.setdefault(
            "quality",
            int(legacy_quality) if legacy_quality is not None else self.DEFAULT_QUALITY,
        )
        encoding["videoCodec"] = "auto"
        encoding.setdefault("preferredCodecs", list(self.PREFERRED_CODECS))


class CleanCaptureMigration(ConfigMigration):
    version = 4
    reason = (
        "footage is now captured before the Panorama UI is drawn, so no HUD, "
        "avatars, toasts or MVP panel end up in the clip"
    )

    def apply(self, raw: dict[str, Any]) -> None:
        recording = raw.setdefault("recording", {})
        recording["captureMode"] = "clean"
        self.console_variables(raw)["spec_autodirector"] = "0"


class SpectateSequenceMigration(ConfigMigration):
    version = 5
    reason = (
        "the camera is now switched with spec_player before being locked, because "
        "spec_lock_to_accountid alone never moves the observer onto a target"
    )
    SPECTATE_COMMANDS = [
        "spec_autodirector 0",
        'spec_player "{player_name}"',
        "spec_lock_to_accountid {account_id}",
    ]
    CROSSHAIR_DEFAULTS = {
        "enabled": True,
        "length": 10,
        "gap": 4,
        "thickness": 2,
        "color": "0x00FF00",
        "opacity": 0.9,
        "outline": 1,
        "outlineColor": "black",
        "dot": False,
    }

    def apply(self, raw: dict[str, Any]) -> None:
        recording = raw.setdefault("recording", {})
        recording.pop("spectateCommandTemplate", None)
        recording["spectateCommands"] = list(self.SPECTATE_COMMANDS)
        raw.setdefault("crosshair", dict(self.CROSSHAIR_DEFAULTS))


class SpectateBySlotMigration(ConfigMigration):
    version = 6
    reason = (
        "the camera is aimed with spec_player <slot> and spec_mode must come first, "
        "otherwise the observer stays stuck in free mode"
    )
    SPECTATE_COMMANDS = [
        "spec_autodirector 0",
        "spec_mode 1",
        "spec_player {slot}",
        "spec_lock_to_accountid {account_id}",
    ]
    QUIET_SCREEN_VARIABLES = {
        "cl_demo_predict": "0",
        "cl_trueview_show_status": "0",
        "cl_hud_telemetry_frametime_show": "0",
        "cl_hud_telemetry_net_misdelivery_show": "0",
        "cl_hud_telemetry_ping_show": "0",
        "cl_hud_telemetry_serverrecvmargin_graph_show": "0",
        "r_show_build_info": "0",
    }

    def apply(self, raw: dict[str, Any]) -> None:
        recording = raw.setdefault("recording", {})
        recording["spectateCommands"] = list(self.SPECTATE_COMMANDS)
        self.console_variables(raw).update(self.QUIET_SCREEN_VARIABLES)


class GameCrosshairMigration(ConfigMigration):
    version = 7
    reason = (
        "the game's own crosshair is kept with cl_draw_only_deathnotices instead of "
        "being painted on afterwards, so it still disappears under the AWP scope"
    )

    def apply(self, raw: dict[str, Any]) -> None:
        recording = raw.setdefault("recording", {})
        recording.pop("hideHud", None)
        recording.pop("hideCrosshair", None)
        recording["captureMode"] = "crosshair"
        recording.setdefault("showKillfeed", False)

        self.console_variables(raw).pop("cl_draw_only_deathnotices", None)
        raw.setdefault("crosshair", {})["enabled"] = False


class KillfeedMigration(ConfigMigration):
    version = 8
    reason = "the kill feed is now shown next to the crosshair"

    def apply(self, raw: dict[str, Any]) -> None:
        raw.setdefault("recording", {})["showKillfeed"] = True


class NadeTimingMigration(ConfigMigration):
    version = 9
    reason = (
        "the zoom hold is counted in real demo ticks and lasts a full second, and a "
        "long grenade flight is trimmed instead of being filmed end to end"
    )
    TIMINGS = {
        "freezeLeadSeconds": 1.0,
        "freezeSeconds": 1.0,
        "landingCutSeconds": 0.5,
        "landingLeadSeconds": 3.0,
    }

    def apply(self, raw: dict[str, Any]) -> None:
        nades = raw.setdefault("nades", {})
        nades.pop("freezeTimescale", None)
        nades.update(self.TIMINGS)


class WarmGameSessionMigration(ConfigMigration):
    version = 10
    reason = (
        "the game can now be left running between recordings, so the next batch is "
        "handed to it through a cfg instead of paying the CS2 startup again"
    )
    SETTINGS = {
        "keepGameOpen": False,
        "handoverIntervalSeconds": 1.0,
        "handoverTimeoutSeconds": 120.0,
        "takeSettleSeconds": 2.0,
        "takeStallSeconds": 120.0,
    }

    def apply(self, raw: dict[str, Any]) -> None:
        recording = raw.setdefault("recording", {})
        for key, value in self.SETTINGS.items():
            recording.setdefault(key, value)


class DemoHandoverChannelMigration(ConfigMigration):
    version = 11
    reason = (
        "a kept open game now closes the demo and goes back to the main menu, and the "
        "next batch is handed to it over the game console instead of a demo tick"
    )

    def apply(self, raw: dict[str, Any]) -> None:
        recording = raw.setdefault("recording", {})
        recording["handoverChannel"] = "netcon"
        recording["handoverTimeoutSeconds"] = 120.0
        raw.setdefault("game", {}).setdefault("netconPort", 0)


class SelfUpdateMigration(ConfigMigration):
    version = 12
    reason = "the app can now check GitHub for a new release and install it itself"
    SETTINGS = {
        "releaseApiUrl": (
            "https://api.github.com/repos/Sevelinish/CS2Prak-HighlightMaker/releases/latest"
        ),
        "assetPattern": "*.zip",
        "checkOnStart": False,
        "relaunchAfterInstall": False,
        "timeoutSeconds": 600,
    }

    def apply(self, raw: dict[str, Any]) -> None:
        update = raw.setdefault("update", {})
        for key, value in self.SETTINGS.items():
            update.setdefault(key, value)


class FlightCameraMigration(ConfigMigration):
    version = 13
    reason = (
        "the landing camera now follows the line the grenade actually flew in on, "
        "so it no longer ends up behind the wall the grenade was thrown over"
    )
    SETTINGS = {"cameraMode": "flight", "minimumApproach": 60.0}

    def apply(self, raw: dict[str, Any]) -> None:
        nades = raw.setdefault("nades", {})
        for key, value in self.SETTINGS.items():
            nades[key] = value


class GroupedThrowMigration(ConfigMigration):
    version = 14
    reason = (
        "throws that share a stretch of the demo are filmed as one clip now, so the "
        "recordings no longer cut each other short"
    )

    def apply(self, raw: dict[str, Any]) -> None:
        raw.setdefault("nades", {}).setdefault("maximumGroupSpread", 600.0)


class ChaseCameraMigration(ConfigMigration):
    version = 15
    reason = "the camera can now fly behind a grenade from the throw to the detonation"
    SETTINGS = {
        "followFlight": False,
        "flyDistance": 110.0,
        "flyHeight": 20.0,
        "flySampleStride": 4,
    }

    def apply(self, raw: dict[str, Any]) -> None:
        nades = raw.setdefault("nades", {})
        for key, value in self.SETTINGS.items():
            nades.setdefault(key, value)


class SpawnThrowMigration(ConfigMigration):
    version = 16
    reason = (
        "a grenade thrown straight out of spawn is now filmed from inside the freeze "
        "time, so the aim up before the round starts is in the clip"
    )
    SETTINGS = {"spawnWindowSeconds": 4.0, "spawnLeadSeconds": 6.0}

    def apply(self, raw: dict[str, Any]) -> None:
        nades = raw.setdefault("nades", {})
        for key, value in self.SETTINGS.items():
            nades.setdefault(key, value)


class EnemyViewMigration(ConfigMigration):
    version = 17
    reason = "a clip can now replay each kill from the victim's own eyes after the player view"
    SETTINGS = {
        "recordEnemyView": False,
        "enemyLeadSeconds": 2.5,
        "enemyHoldSeconds": 1.5,
    }

    def apply(self, raw: dict[str, Any]) -> None:
        recording = raw.setdefault("recording", {})
        for key, value in self.SETTINGS.items():
            recording.setdefault(key, value)


MIGRATIONS: tuple[ConfigMigration, ...] = (
    Cs2CustomLoaderMigration(),
    Cs2ClipQualityMigration(),
    CleanCaptureMigration(),
    SpectateSequenceMigration(),
    SpectateBySlotMigration(),
    GameCrosshairMigration(),
    KillfeedMigration(),
    NadeTimingMigration(),
    WarmGameSessionMigration(),
    DemoHandoverChannelMigration(),
    SelfUpdateMigration(),
    FlightCameraMigration(),
    GroupedThrowMigration(),
    ChaseCameraMigration(),
    SpawnThrowMigration(),
    EnemyViewMigration(),
)
CURRENT_VERSION = max((migration.version for migration in MIGRATIONS), default=INITIAL_VERSION)


class ConfigMigrator:
    def __init__(self, migrations: tuple[ConfigMigration, ...] = MIGRATIONS) -> None:
        self._migrations = sorted(migrations, key=lambda migration: migration.version)
        self._logger = get_logger("config")

    def migrate(self, raw: dict[str, Any]) -> bool:
        stored = self._stored_version(raw)
        if stored >= CURRENT_VERSION:
            return False

        for migration in self._migrations:
            if migration.version > stored:
                migration.apply(raw)
                self._logger.info(
                    "Updated config.json to version %d: %s", migration.version, migration.reason
                )

        raw[VERSION_KEY] = CURRENT_VERSION
        return True

    @staticmethod
    def _stored_version(raw: dict[str, Any]) -> int:
        try:
            return int(raw.get(VERSION_KEY, INITIAL_VERSION))
        except (TypeError, ValueError):
            return INITIAL_VERSION
