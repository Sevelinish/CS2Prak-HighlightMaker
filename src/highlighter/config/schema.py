from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

CONFIG_VERSION = 7

DEFAULT_TAG_WEIGHTS: dict[str, float] = {
    "kills_2": 4.0,
    "kills_3": 12.0,
    "kills_4": 22.0,
    "kills_5": 40.0,
    "awp_double": 8.0,
    "awp_multi": 16.0,
    "sniper_noscope_multi": 10.0,
    "knife_kill": 14.0,
    "zeus_kill": 12.0,
    "deagle_headshot": 6.0,
    "pistol_multi": 9.0,
    "grenade_kill": 5.0,
    "clutch_1v2": 10.0,
    "clutch_1v3": 20.0,
    "clutch_1v4": 30.0,
    "clutch_1v5": 45.0,
    "noscope": 9.0,
    "wallbang": 7.0,
    "through_smoke": 5.0,
    "blind_kill": 6.0,
    "airborne_kill": 8.0,
    "headshot_only": 5.0,
    "pistol_round": 3.0,
}


def _read(source: Mapping[str, Any], key: str, fallback: Any) -> Any:
    value = source.get(key)
    return fallback if value is None else value


def _merged_strings(defaults: Mapping[str, str], overrides: Any) -> dict[str, str]:
    merged = {str(key): str(value) for key, value in defaults.items()}
    if isinstance(overrides, Mapping):
        merged.update({str(key): str(value) for key, value in overrides.items()})
    return merged


@dataclass(slots=True)
class PathsConfig:
    cs2_directory: str = ""
    hlae_executable: str = ""
    ffmpeg_executable: str = ""
    demo_directory: str = "demos"
    output_directory: str = "Highlighter"
    tools_directory: str = "tools"
    work_directory: str = "work"

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "PathsConfig":
        default = cls()
        return cls(
            cs2_directory=str(_read(source, "cs2Directory", default.cs2_directory)),
            hlae_executable=str(_read(source, "hlaeExecutable", default.hlae_executable)),
            ffmpeg_executable=str(_read(source, "ffmpegExecutable", default.ffmpeg_executable)),
            demo_directory=str(_read(source, "demoDirectory", default.demo_directory)),
            output_directory=str(_read(source, "outputDirectory", default.output_directory)),
            tools_directory=str(_read(source, "toolsDirectory", default.tools_directory)),
            work_directory=str(_read(source, "workDirectory", default.work_directory)),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "cs2Directory": self.cs2_directory,
            "hlaeExecutable": self.hlae_executable,
            "ffmpegExecutable": self.ffmpeg_executable,
            "demoDirectory": self.demo_directory,
            "outputDirectory": self.output_directory,
            "toolsDirectory": self.tools_directory,
            "workDirectory": self.work_directory,
        }


@dataclass(slots=True)
class RecordingConfig:
    fps: int = 60
    width: int = 1920
    height: int = 1080
    fullscreen: bool = False
    lead_in_seconds: float = 2.0
    resume_lead_seconds: float = 1.5
    gap_hold_seconds: float = 4.0
    post_roll_seconds: float = 2.5
    max_clip_seconds: float = 90.0
    spectator_mode: str = "first_person"
    spectate_commands: list[str] = field(
        default_factory=lambda: [
            "spec_autodirector 0",
            "spec_mode 1",
            "spec_player {slot}",
            "spec_lock_to_accountid {account_id}",
        ]
    )
    seek_lead_ticks: int = 128
    playback_speed: float = 1.0
    skip_dead_time: bool = True
    capture_mode: str = "crosshair"
    show_killfeed: bool = False
    close_game_when_done: bool = True
    open_output_folder: bool = True

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "RecordingConfig":
        default = cls()
        return cls(
            fps=int(_read(source, "fps", default.fps)),
            width=int(_read(source, "width", default.width)),
            height=int(_read(source, "height", default.height)),
            fullscreen=bool(_read(source, "fullscreen", default.fullscreen)),
            lead_in_seconds=float(_read(source, "leadInSeconds", default.lead_in_seconds)),
            resume_lead_seconds=float(
                _read(source, "resumeLeadSeconds", default.resume_lead_seconds)
            ),
            gap_hold_seconds=float(_read(source, "gapHoldSeconds", default.gap_hold_seconds)),
            post_roll_seconds=float(_read(source, "postRollSeconds", default.post_roll_seconds)),
            max_clip_seconds=float(_read(source, "maxClipSeconds", default.max_clip_seconds)),
            spectator_mode=str(_read(source, "spectatorMode", default.spectator_mode)),
            spectate_commands=[
                str(item) for item in _read(source, "spectateCommands", default.spectate_commands)
            ],
            seek_lead_ticks=int(_read(source, "seekLeadTicks", default.seek_lead_ticks)),
            playback_speed=float(_read(source, "playbackSpeed", default.playback_speed)),
            skip_dead_time=bool(_read(source, "skipDeadTime", default.skip_dead_time)),
            capture_mode=str(_read(source, "captureMode", default.capture_mode)),
            show_killfeed=bool(_read(source, "showKillfeed", default.show_killfeed)),
            close_game_when_done=bool(
                _read(source, "closeGameWhenDone", default.close_game_when_done)
            ),
            open_output_folder=bool(
                _read(source, "openOutputFolder", default.open_output_folder)
            ),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
            "fullscreen": self.fullscreen,
            "leadInSeconds": self.lead_in_seconds,
            "resumeLeadSeconds": self.resume_lead_seconds,
            "gapHoldSeconds": self.gap_hold_seconds,
            "postRollSeconds": self.post_roll_seconds,
            "maxClipSeconds": self.max_clip_seconds,
            "spectatorMode": self.spectator_mode,
            "spectateCommands": list(self.spectate_commands),
            "seekLeadTicks": self.seek_lead_ticks,
            "playbackSpeed": self.playback_speed,
            "skipDeadTime": self.skip_dead_time,
            "captureMode": self.capture_mode,
            "showKillfeed": self.show_killfeed,
            "closeGameWhenDone": self.close_game_when_done,
            "openOutputFolder": self.open_output_folder,
        }


@dataclass(slots=True)
class EncodingConfig:
    video_codec: str = "auto"
    preferred_codecs: list[str] = field(
        default_factory=lambda: ["h264_nvenc", "h264_amf", "h264_qsv", "libx264"]
    )
    quality: int = 20
    preset: str = "faster"
    pixel_format: str = "yuv420p"
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    container: str = "mp4"
    extra_output_arguments: list[str] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "EncodingConfig":
        default = cls()
        return cls(
            video_codec=str(_read(source, "videoCodec", default.video_codec)),
            preferred_codecs=[
                str(item) for item in _read(source, "preferredCodecs", default.preferred_codecs)
            ],
            quality=int(_read(source, "quality", default.quality)),
            preset=str(_read(source, "preset", default.preset)),
            pixel_format=str(_read(source, "pixelFormat", default.pixel_format)),
            audio_codec=str(_read(source, "audioCodec", default.audio_codec)),
            audio_bitrate=str(_read(source, "audioBitrate", default.audio_bitrate)),
            container=str(_read(source, "container", default.container)),
            extra_output_arguments=list(
                _read(source, "extraOutputArguments", default.extra_output_arguments)
            ),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "videoCodec": self.video_codec,
            "preferredCodecs": list(self.preferred_codecs),
            "quality": self.quality,
            "preset": self.preset,
            "pixelFormat": self.pixel_format,
            "audioCodec": self.audio_codec,
            "audioBitrate": self.audio_bitrate,
            "container": self.container,
            "extraOutputArguments": list(self.extra_output_arguments),
        }


@dataclass(slots=True)
class CrosshairConfig:
    enabled: bool = False
    length: int = 10
    gap: int = 4
    thickness: int = 2
    color: str = "0x00FF00"
    opacity: float = 0.9
    outline: int = 1
    outline_color: str = "black"
    dot: bool = False

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "CrosshairConfig":
        default = cls()
        return cls(
            enabled=bool(_read(source, "enabled", default.enabled)),
            length=int(_read(source, "length", default.length)),
            gap=int(_read(source, "gap", default.gap)),
            thickness=int(_read(source, "thickness", default.thickness)),
            color=str(_read(source, "color", default.color)),
            opacity=float(_read(source, "opacity", default.opacity)),
            outline=int(_read(source, "outline", default.outline)),
            outline_color=str(_read(source, "outlineColor", default.outline_color)),
            dot=bool(_read(source, "dot", default.dot)),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "length": self.length,
            "gap": self.gap,
            "thickness": self.thickness,
            "color": self.color,
            "opacity": self.opacity,
            "outline": self.outline,
            "outlineColor": self.outline_color,
            "dot": self.dot,
        }


@dataclass(slots=True)
class DetectionConfig:
    minimum_score: float = 10.0
    minimum_kills: int = 2
    maximum_highlights: int = 40
    tag_weights: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_TAG_WEIGHTS)
    )
    enabled_rules: list[str] = field(
        default_factory=lambda: ["multi_kill", "weapon_feat", "clutch", "trick_shot"]
    )

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "DetectionConfig":
        default = cls()
        weights = dict(DEFAULT_TAG_WEIGHTS)
        weights.update(_read(source, "tagWeights", {}) or {})
        return cls(
            minimum_score=float(_read(source, "minimumScore", default.minimum_score)),
            minimum_kills=int(_read(source, "minimumKills", default.minimum_kills)),
            maximum_highlights=int(
                _read(source, "maximumHighlights", default.maximum_highlights)
            ),
            tag_weights={str(key): float(value) for key, value in weights.items()},
            enabled_rules=[str(name) for name in _read(source, "enabledRules", default.enabled_rules)],
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "minimumScore": self.minimum_score,
            "minimumKills": self.minimum_kills,
            "maximumHighlights": self.maximum_highlights,
            "enabledRules": list(self.enabled_rules),
            "tagWeights": dict(self.tag_weights),
        }

    def weight_of(self, tag_code: str) -> float:
        return float(self.tag_weights.get(tag_code, DEFAULT_TAG_WEIGHTS.get(tag_code, 0.0)))


@dataclass(slots=True)
class GameConfig:
    tick_rate: int = 64
    launch_arguments: list[str] = field(
        default_factory=lambda: [
            "-steam",
            "-insecure",
            "-afxDisableSteamStorage",
            "-novid",
            "-console",
        ]
    )
    hook_dll_relative_path: str = "x64/AfxHookSource2.dll"
    steam_environment: dict[str, str] = field(
        default_factory=lambda: {
            "SteamAppId": "730",
            "SteamGameId": "730",
            "SteamOverlayGameId": "730",
            "SteamClientLaunch": "1",
        }
    )
    console_variables: dict[str, str] = field(
        default_factory=lambda: {
            "fps_max": "0",
            "engine_no_focus_sleep": "0",
            "snd_mute_losefocus": "0",
            "cl_demo_predict": "0",
            "demo_ui_mode": "0",
            "spec_show_xray": "0",
            "spec_autodirector": "0",
            "cl_trueview_show_status": "0",
            "cl_hud_telemetry_frametime_show": "0",
            "cl_hud_telemetry_net_misdelivery_show": "0",
            "cl_hud_telemetry_ping_show": "0",
            "cl_hud_telemetry_serverrecvmargin_graph_show": "0",
            "r_show_build_info": "0",
            "sv_cheats": "1",
            "cl_showfps": "0",
            "volume": "0.35",
        }
    )
    game_startup_timeout_seconds: int = 300
    recording_timeout_minutes: int = 120
    apply_high_graphics: bool = True
    restore_graphics_on_exit: bool = True
    hlae_argument_template: list[str] = field(
        default_factory=lambda: [
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
    )

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "GameConfig":
        default = cls()
        return cls(
            tick_rate=int(_read(source, "tickRate", default.tick_rate)),
            launch_arguments=[
                str(item) for item in _read(source, "launchArguments", default.launch_arguments)
            ],
            hook_dll_relative_path=str(
                _read(source, "hookDllRelativePath", default.hook_dll_relative_path)
            ),
            steam_environment=_merged_strings(
                default.steam_environment, source.get("steamEnvironment")
            ),
            console_variables=_merged_strings(
                default.console_variables, source.get("consoleVariables")
            ),
            game_startup_timeout_seconds=int(
                _read(
                    source,
                    "gameStartupTimeoutSeconds",
                    default.game_startup_timeout_seconds,
                )
            ),
            recording_timeout_minutes=int(
                _read(source, "recordingTimeoutMinutes", default.recording_timeout_minutes)
            ),
            hlae_argument_template=[
                str(item)
                for item in _read(source, "hlaeArgumentTemplate", default.hlae_argument_template)
            ],
            apply_high_graphics=bool(
                _read(source, "applyHighGraphics", default.apply_high_graphics)
            ),
            restore_graphics_on_exit=bool(
                _read(source, "restoreGraphicsOnExit", default.restore_graphics_on_exit)
            ),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "tickRate": self.tick_rate,
            "launchArguments": list(self.launch_arguments),
            "hookDllRelativePath": self.hook_dll_relative_path,
            "steamEnvironment": dict(self.steam_environment),
            "consoleVariables": dict(self.console_variables),
            "gameStartupTimeoutSeconds": self.game_startup_timeout_seconds,
            "recordingTimeoutMinutes": self.recording_timeout_minutes,
            "applyHighGraphics": self.apply_high_graphics,
            "restoreGraphicsOnExit": self.restore_graphics_on_exit,
            "hlaeArgumentTemplate": list(self.hlae_argument_template),
        }


@dataclass(slots=True)
class ToolchainConfig:
    auto_download: bool = True
    hlae_download_url: str = ""
    hlae_release_api_url: str = (
        "https://api.github.com/repos/advancedfx/advancedfx/releases/latest"
    )
    hlae_asset_pattern: str = "hlae_*.zip"
    ffmpeg_download_url: str = (
        "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    )
    download_timeout_seconds: int = 600

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "ToolchainConfig":
        default = cls()
        return cls(
            auto_download=bool(_read(source, "autoDownload", default.auto_download)),
            hlae_download_url=str(_read(source, "hlaeDownloadUrl", default.hlae_download_url)),
            hlae_release_api_url=str(
                _read(source, "hlaeReleaseApiUrl", default.hlae_release_api_url)
            ),
            hlae_asset_pattern=str(_read(source, "hlaeAssetPattern", default.hlae_asset_pattern)),
            ffmpeg_download_url=str(
                _read(source, "ffmpegDownloadUrl", default.ffmpeg_download_url)
            ),
            download_timeout_seconds=int(
                _read(source, "downloadTimeoutSeconds", default.download_timeout_seconds)
            ),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "autoDownload": self.auto_download,
            "hlaeDownloadUrl": self.hlae_download_url,
            "hlaeReleaseApiUrl": self.hlae_release_api_url,
            "hlaeAssetPattern": self.hlae_asset_pattern,
            "ffmpegDownloadUrl": self.ffmpeg_download_url,
            "downloadTimeoutSeconds": self.download_timeout_seconds,
        }


@dataclass(slots=True)
class ApplicationConfig:
    debug: bool = False
    paths: PathsConfig = field(default_factory=PathsConfig)
    recording: RecordingConfig = field(default_factory=RecordingConfig)
    encoding: EncodingConfig = field(default_factory=EncodingConfig)
    crosshair: CrosshairConfig = field(default_factory=CrosshairConfig)
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    game: GameConfig = field(default_factory=GameConfig)
    toolchain: ToolchainConfig = field(default_factory=ToolchainConfig)

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "ApplicationConfig":
        return cls(
            debug=bool(_read(source, "debug", cls().debug)),
            paths=PathsConfig.from_mapping(source.get("paths") or {}),
            recording=RecordingConfig.from_mapping(source.get("recording") or {}),
            encoding=EncodingConfig.from_mapping(source.get("encoding") or {}),
            crosshair=CrosshairConfig.from_mapping(source.get("crosshair") or {}),
            detection=DetectionConfig.from_mapping(source.get("detection") or {}),
            game=GameConfig.from_mapping(source.get("game") or {}),
            toolchain=ToolchainConfig.from_mapping(source.get("toolchain") or {}),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "version": CONFIG_VERSION,
            "debug": self.debug,
            "paths": self.paths.to_mapping(),
            "recording": self.recording.to_mapping(),
            "encoding": self.encoding.to_mapping(),
            "crosshair": self.crosshair.to_mapping(),
            "detection": self.detection.to_mapping(),
            "game": self.game.to_mapping(),
            "toolchain": self.toolchain.to_mapping(),
        }
