from __future__ import annotations

from typing import Any, Mapping

from ..config.schema import ApplicationConfig
from .errors import BadRequestError

READ_ONLY_KEYS = frozenset({"version"})


class ConfigMerger:
    @classmethod
    def merge(cls, base: Mapping[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
        merged = dict(base)
        for key, value in patch.items():
            if key in READ_ONLY_KEYS:
                continue
            current = merged.get(key)
            if isinstance(value, Mapping) and isinstance(current, Mapping):
                merged[key] = cls.merge(current, value)
            else:
                merged[key] = value
        return merged

    @classmethod
    def apply(cls, config: ApplicationConfig, patch: Any) -> ApplicationConfig:
        if patch is None:
            return config
        if not isinstance(patch, Mapping):
            raise BadRequestError("Configuration overrides must be a JSON object")
        try:
            return ApplicationConfig.from_mapping(cls.merge(config.to_mapping(), patch))
        except (TypeError, ValueError) as error:
            raise BadRequestError(f"Configuration overrides are not valid: {error}") from error


class FieldKind:
    BOOLEAN = "boolean"
    INTEGER = "integer"
    NUMBER = "number"
    TEXT = "text"
    CHOICE = "choice"
    PATH = "path"
    LIST = "list"
    MAP = "map"


class ConfigSchema:
    FIELDS: tuple[tuple[str, str, str, str], ...] = (
        ("debug", FieldKind.BOOLEAN, "", "Write debug lines to the log and the console"),
        ("paths.cs2Directory", FieldKind.PATH, "", "CS2 install folder, empty means auto detect"),
        ("paths.hlaeExecutable", FieldKind.PATH, "", "HLAE.exe, empty means auto download"),
        ("paths.ffmpegExecutable", FieldKind.PATH, "", "ffmpeg.exe, empty means auto download"),
        ("paths.demoDirectory", FieldKind.PATH, "", "Folder scanned for demos"),
        ("paths.outputDirectory", FieldKind.PATH, "", "Folder the finished videos are written to"),
        ("paths.toolsDirectory", FieldKind.PATH, "", "Folder HLAE and ffmpeg are installed into"),
        ("paths.workDirectory", FieldKind.PATH, "", "Scratch folder for takes, scripts and plans"),
        ("recording.fps", FieldKind.INTEGER, "fps", "Frames per second of the captured video"),
        ("recording.width", FieldKind.INTEGER, "px", "Game window width while recording"),
        ("recording.height", FieldKind.INTEGER, "px", "Game window height while recording"),
        ("recording.fullscreen", FieldKind.BOOLEAN, "", "Run the game fullscreen instead of windowed"),
        ("recording.leadInSeconds", FieldKind.NUMBER, "s", "Recorded time before the first kill"),
        ("recording.resumeLeadSeconds", FieldKind.NUMBER, "s", "Recorded time before a later kill"),
        ("recording.gapHoldSeconds", FieldKind.NUMBER, "s", "Dead time kept before a clip is split"),
        ("recording.postRollSeconds", FieldKind.NUMBER, "s", "Recorded time after the last kill"),
        ("recording.maxClipSeconds", FieldKind.NUMBER, "s", "Hard ceiling for a single clip"),
        ("recording.spectatorMode", FieldKind.CHOICE, "", "fixed, first_person, third_person, free"),
        ("recording.spectateCommands", FieldKind.LIST, "", "Console commands that aim the camera"),
        ("recording.seekLeadTicks", FieldKind.INTEGER, "ticks", "Ticks of runway before a seek target"),
        ("recording.playbackSpeed", FieldKind.NUMBER, "x", "host_timescale applied during playback"),
        ("recording.skipDeadTime", FieldKind.BOOLEAN, "", "Seek over the gaps between segments"),
        ("recording.captureMode", FieldKind.CHOICE, "", "clean or crosshair"),
        ("recording.showKillfeed", FieldKind.BOOLEAN, "", "Keep the kill feed in crosshair mode"),
        ("recording.closeGameWhenDone", FieldKind.BOOLEAN, "", "Quit CS2 after the last clip"),
        ("recording.openOutputFolder", FieldKind.BOOLEAN, "", "Open the output folder when finished"),
        ("recording.singleFile", FieldKind.BOOLEAN, "", "Join every clip into one video"),
        ("recording.recordEnemyView", FieldKind.BOOLEAN, "", "Replay every kill from the victim's eyes after the player view"),
        ("recording.enemyLeadSeconds", FieldKind.NUMBER, "s", "Recorded time before a kill in the victim view"),
        ("recording.enemyHoldSeconds", FieldKind.NUMBER, "s", "Recorded time after a kill in the victim view"),
        ("recording.keepGameOpen", FieldKind.BOOLEAN, "", "Leave CS2 running for the next job"),
        ("recording.handoverChannel", FieldKind.CHOICE, "", "netcon closes the demo, demo keeps it playing"),
        ("recording.handoverIntervalSeconds", FieldKind.NUMBER, "s", "How often the running game looks for a new script"),
        ("recording.handoverTimeoutSeconds", FieldKind.NUMBER, "s", "How long to wait for the running game to answer"),
        ("recording.takeSettleSeconds", FieldKind.NUMBER, "s", "How long a take must stop growing before it counts as done"),
        ("recording.takeStallSeconds", FieldKind.NUMBER, "s", "How long to wait on a recording that stopped producing"),
        ("encoding.videoCodec", FieldKind.CHOICE, "", "auto or an explicit ffmpeg encoder"),
        ("encoding.preferredCodecs", FieldKind.LIST, "", "Encoder probe order when videoCodec is auto"),
        ("encoding.quality", FieldKind.INTEGER, "crf", "Lower is better quality and a larger file"),
        ("encoding.container", FieldKind.TEXT, "", "Output container extension"),
        ("crosshair.enabled", FieldKind.BOOLEAN, "", "Paint a crosshair over the finished video"),
        ("nades.leadInSeconds", FieldKind.NUMBER, "s", "Recorded time before the throw"),
        ("nades.spawnWindowSeconds", FieldKind.NUMBER, "s", "A throw this soon after the round starts counts as a spawn throw"),
        ("nades.spawnLeadSeconds", FieldKind.NUMBER, "s", "Run up for a spawn throw, reaching into the freeze time"),
        ("nades.freezeLeadSeconds", FieldKind.NUMBER, "s", "When the zoom hold starts before the throw"),
        ("nades.freezeSeconds", FieldKind.NUMBER, "s", "How long the zoomed view is held"),
        ("nades.zoomFov", FieldKind.NUMBER, "fov", "Field of view during the zoom hold"),
        ("nades.cameraMode", FieldKind.CHOICE, "", "flight follows the grenade in, thrower sits on the throw line"),
        ("nades.minimumApproach", FieldKind.NUMBER, "units", "How much clear flight is needed before it is trusted"),
        ("nades.maximumGroupSpread", FieldKind.NUMBER, "units", "How far apart landings can be and still share one shot"),
        ("nades.followFlight", FieldKind.BOOLEAN, "", "Fly behind the grenade from the throw to the detonation"),
        ("nades.flyDistance", FieldKind.NUMBER, "units", "How far behind the grenade the chase camera sits"),
        ("nades.flyHeight", FieldKind.NUMBER, "units", "How high above its path the chase camera sits"),
        ("nades.flySampleStride", FieldKind.INTEGER, "ticks", "How often the flight is sampled into a keyframe"),
        ("nades.landingCutSeconds", FieldKind.NUMBER, "s", "Delay before cutting to the landing spot"),
        ("nades.landingLeadSeconds", FieldKind.NUMBER, "s", "Flight kept before detonation when trimmed"),
        ("nades.landingHoldSeconds", FieldKind.NUMBER, "s", "Recorded time after detonation"),
        ("nades.landingDistance", FieldKind.NUMBER, "units", "Camera distance from the landing spot"),
        ("nades.landingHeight", FieldKind.NUMBER, "units", "Camera height above the landing spot"),
        ("nades.calloutSampleStride", FieldKind.INTEGER, "ticks", "Sampling stride of the callout atlas"),
        ("detection.minimumScore", FieldKind.NUMBER, "", "Score a round must reach to be offered"),
        ("detection.minimumKills", FieldKind.INTEGER, "", "Kills a round must reach to be offered"),
        ("detection.maximumHighlights", FieldKind.INTEGER, "", "Ceiling on the number of highlights"),
        ("detection.tagWeights", FieldKind.MAP, "", "Score contributed by each detected tag"),
        ("detection.enabledRules", FieldKind.LIST, "", "Detection rules that are allowed to run"),
        ("game.tickRate", FieldKind.INTEGER, "tick", "Fallback tick rate when the demo omits it"),
        ("game.consoleVariables", FieldKind.MAP, "", "Cvars applied before recording starts"),
        ("game.netconPort", FieldKind.INTEGER, "port", "Console port for a kept open game, 0 picks a free one"),
        ("game.launchArguments", FieldKind.LIST, "", "Command line passed to cs2.exe"),
        ("game.gameStartupTimeoutSeconds", FieldKind.INTEGER, "s", "How long to wait for cs2.exe"),
        ("game.recordingTimeoutMinutes", FieldKind.INTEGER, "min", "Hard ceiling on one recording run"),
        ("toolchain.autoDownload", FieldKind.BOOLEAN, "", "Fetch HLAE and ffmpeg when missing"),
        ("update.releaseApiUrl", FieldKind.TEXT, "", "Release feed checked for a newer version"),
        ("update.assetPattern", FieldKind.TEXT, "", "Which release file holds the program"),
        ("update.checkOnStart", FieldKind.BOOLEAN, "", "Look for a newer version on every run"),
        ("update.relaunchAfterInstall", FieldKind.BOOLEAN, "", "Start the new version once it is installed"),
        ("update.timeoutSeconds", FieldKind.INTEGER, "s", "Network timeout for the update download"),
    )

    @classmethod
    def describe(cls) -> dict[str, Any]:
        defaults = ApplicationConfig().to_mapping()
        return {
            "fields": [
                {
                    "path": path,
                    "kind": kind,
                    "unit": unit,
                    "description": description,
                    "default": cls._default(defaults, path),
                }
                for path, kind, unit, description in cls.FIELDS
            ]
        }

    @staticmethod
    def _default(defaults: Mapping[str, Any], path: str) -> Any:
        current: Any = defaults
        for segment in path.split("."):
            if not isinstance(current, Mapping) or segment not in current:
                return None
            current = current[segment]
        return current
