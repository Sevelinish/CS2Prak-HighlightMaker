from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config.schema import GameConfig, RecordingConfig
from ..media.encoders import EncoderProfile
from ..plan.models import ClipSegment, ClipSpec, RecordingPlan

SESSION_SCRIPT_NAME = "highlighter_session"
SEEK_SCRIPT_NAME = "highlighter_seek"
STREAM_SETTINGS_NAME = "highlighterFfmpeg"
VIDEO_FILE_STEM = "video"
CLEAN_STREAM_NAME = "highlighterClean"
CLEAN_CAPTURE_MODE = "clean"
CROSSHAIR_CAPTURE_MODE = "crosshair"
BOOTSTRAP_TICK = 64

SPECTATOR_MODES = {
    "fixed": 1,
    "first_person": 2,
    "third_person": 3,
    "free": 4,
}
DEFAULT_SPECTATOR_MODE = SPECTATOR_MODES["first_person"]


@dataclass(frozen=True, slots=True)
class ScriptFile:
    name: str
    content: str

    @property
    def file_name(self) -> str:
        return f"{self.name}.cfg"


@dataclass(frozen=True, slots=True)
class ScriptBundle:
    files: tuple[ScriptFile, ...]
    entry_script: str


@dataclass(frozen=True, slots=True)
class ScheduledSegment:
    clip: ClipSpec
    segment: ClipSegment

    @property
    def start_script_name(self) -> str:
        return f"highlighter_c{self.clip.index:02d}_{self.segment.name}_start"

    @property
    def end_script_name(self) -> str:
        return f"highlighter_c{self.clip.index:02d}_{self.segment.name}_end"


class MirvScriptBuilder:
    def __init__(
        self,
        recording: RecordingConfig,
        encoder: EncoderProfile,
        game: GameConfig,
        take_directory: Path,
    ) -> None:
        self._recording = recording
        self._encoder = encoder
        self._game = game
        self._take_directory = take_directory

    def build(self, plan: RecordingPlan) -> ScriptBundle:
        schedule = self._flatten(plan)
        files = [ScriptFile(SESSION_SCRIPT_NAME, self._session_script(schedule))]

        if schedule:
            files.append(ScriptFile(SEEK_SCRIPT_NAME, self._seek_script(schedule[0])))

        for position, entry in enumerate(schedule):
            following = schedule[position + 1] if position + 1 < len(schedule) else None
            files.append(ScriptFile(entry.start_script_name, self._start_script(entry)))
            files.append(ScriptFile(entry.end_script_name, self._end_script(entry, following)))

        return ScriptBundle(files=tuple(files), entry_script=SESSION_SCRIPT_NAME)

    @staticmethod
    def _flatten(plan: RecordingPlan) -> list[ScheduledSegment]:
        return [
            ScheduledSegment(clip=clip, segment=segment)
            for clip in plan.clips
            for segment in clip.segments
        ]

    def _session_script(self, schedule: list[ScheduledSegment]) -> str:
        lines = [f"{name} {value}" for name, value in self._game.console_variables.items()]
        lines.extend(
            [
                f"host_timescale {self._recording.playback_speed:g}",
                f"mirv_streams settings add ffmpeg {STREAM_SETTINGS_NAME} "
                f'"{self._ffmpeg_arguments()}"',
                *self._capture_setup(),
                "mirv_streams record startMovieWav 1",
                f"mirv_streams record fps {self._recording.fps}",
                "mirv_cmd clear",
            ]
        )

        if schedule:
            lines.append(f"mirv_cmd addAtTick {BOOTSTRAP_TICK} exec {SEEK_SCRIPT_NAME}")

        for entry in schedule:
            lines.append(
                f"mirv_cmd addAtTick {entry.segment.start_tick} exec {entry.start_script_name}"
            )
            lines.append(
                f"mirv_cmd addAtTick {entry.segment.end_tick} exec {entry.end_script_name}"
            )

        return self._join(lines)

    def _capture_setup(self) -> list[str]:
        if self._recording.capture_mode == CLEAN_CAPTURE_MODE:
            return [
                "mirv_streams record screen enabled 0",
                f"mirv_streams add normal {CLEAN_STREAM_NAME}",
                f"mirv_streams edit {CLEAN_STREAM_NAME} record 1",
                f"mirv_streams edit {CLEAN_STREAM_NAME} capture beforeUi",
                f"mirv_streams edit {CLEAN_STREAM_NAME} settings {STREAM_SETTINGS_NAME}",
            ]

        moviemaking = self._recording.capture_mode == CROSSHAIR_CAPTURE_MODE
        return [
            "mirv_streams record screen enabled 1",
            f"mirv_streams record screen settings {STREAM_SETTINGS_NAME}",
            "cl_drawhud 1",
            f"cl_draw_only_deathnotices {1 if moviemaking else 0}",
            f"cl_drawhud_force_deathnotices {self._deathnotice_mode(moviemaking)}",
        ]

    def _deathnotice_mode(self, moviemaking: bool) -> int:
        if not moviemaking:
            return 0
        return 1 if self._recording.show_killfeed else -1

    def _seek_script(self, first: ScheduledSegment) -> str:
        return self._join(["demo_resume", self._forward_seek(BOOTSTRAP_TICK, first)])

    def _start_script(self, entry: ScheduledSegment) -> str:
        take_path = self._take_directory / entry.clip.name / entry.segment.name
        return self._join(
            [
                *self._spectate_commands(entry.clip),
                f"spec_mode {self._spectator_mode()}",
                f'mirv_streams record name "{self._as_engine_path(take_path)}"',
                "mirv_streams record start",
            ]
        )

    def _end_script(self, entry: ScheduledSegment, following: ScheduledSegment | None) -> str:
        lines = ["mirv_streams record end"]
        if following is not None:
            if self._recording.skip_dead_time:
                lines.append(self._forward_seek(entry.segment.end_tick, following))
        elif self._recording.close_game_when_done:
            lines.append("quit")
        return self._join(lines)

    def _forward_seek(self, current_tick: int, target: ScheduledSegment) -> str:
        destination = max(0, target.segment.start_tick - self._recording.seek_lead_ticks)
        if destination <= current_tick:
            return ""
        return f"demo_gototick {destination}" 

    def _spectate_commands(self, clip: ClipSpec) -> list[str]:
        return [
            template.format(
                account_id=clip.player.account_id,
                steam_id64=clip.player.steam_id64,
                slot=clip.player.slot,
                player_name=self._console_safe(clip.player.name),
            )
            for template in self._recording.spectate_commands
        ]

    @staticmethod
    def _console_safe(value: str) -> str:
        return "".join(
            character
            for character in value
            if character.isprintable() and character not in {'"', ";"}
        )

    def _spectator_mode(self) -> int:
        return SPECTATOR_MODES.get(self._recording.spectator_mode, DEFAULT_SPECTATOR_MODE)

    def _ffmpeg_arguments(self) -> str:
        arguments = list(self._encoder.output_arguments())
        arguments.append(
            f"{{QUOTE}}{{AFX_STREAM_PATH}}/{VIDEO_FILE_STEM}."
            f"{self._encoder.container}{{QUOTE}}"
        )
        return " ".join(arguments)

    @staticmethod
    def _as_engine_path(path: Path) -> str:
        return str(path).replace("\\", "/")

    @staticmethod
    def _join(lines: list[str]) -> str:
        return "\n".join(line for line in lines if line) + "\n"
