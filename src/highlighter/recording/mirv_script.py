from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config.schema import GameConfig, RecordingConfig
from ..media.encoders import EncoderProfile
from .campath import CampathDocument
from ..plan.models import CameraBeat, ClipSegment, ClipSpec, RecordingPlan

SESSION_SCRIPT_NAME = "highlighter_session"
SEEK_SCRIPT_NAME = "highlighter_seek"
LISTEN_SCRIPT_NAME = "highlighter_listen"
FINISH_SCRIPT_NAME = "highlighter_finish"
SCRIPT_EXTENSION = ".cfg"
CAMPATH_EXTENSION = ".xml"
CAMPATH_SUFFIX = "_fly"
FLY_SUFFIX = "_flycam"
HANDOVER_SCRIPT_NAME = "highlighter_handover"
LISTEN_START_DELAY_SECONDS = 5.0
MAXIMUM_LISTEN_ENTRIES = 4000
FALLBACK_LISTEN_SECONDS = 600.0
QUIT_DELAY_SECONDS = 3.0
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
    extension: str = SCRIPT_EXTENSION

    @property
    def file_name(self) -> str:
        return f"{self.name}{self.extension}"


@dataclass(frozen=True, slots=True)
class ScriptBundle:
    files: tuple[ScriptFile, ...]
    entry_script: str
    handover_script: str = ""
    listen_script: str = ""

    @property
    def hands_over(self) -> bool:
        return bool(self.handover_script)


@dataclass(frozen=True, slots=True)
class ScheduledBeat:
    clip: ClipSpec
    beat: CameraBeat

    @property
    def script_name(self) -> str:
        return f"highlighter_c{self.clip.index:02d}_{self.beat.name}"


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
        script_directory: Path | None = None,
    ) -> None:
        self._recording = recording
        self._encoder = encoder
        self._game = game
        self._take_directory = take_directory
        self._script_directory = script_directory or Path(".")

    def build(self, plan: RecordingPlan, handover: bool = False) -> ScriptBundle:
        schedule = self._flatten(plan)
        files = [ScriptFile(SESSION_SCRIPT_NAME, self._session_script(plan, schedule))]

        if schedule:
            files.append(ScriptFile(SEEK_SCRIPT_NAME, self._seek_script(schedule[0])))

        if self._recording.keep_game_open:
            files.append(ScriptFile(LISTEN_SCRIPT_NAME, self._listen_script(plan)))
            files.append(ScriptFile(FINISH_SCRIPT_NAME, self.park_script()))

        for position, entry in enumerate(schedule):
            following = schedule[position + 1] if position + 1 < len(schedule) else None
            files.append(ScriptFile(entry.start_script_name, self._start_script(entry)))
            files.append(
                ScriptFile(entry.end_script_name, self._end_script(plan, entry, following))
            )

        for beat in self._beats(plan):
            files.append(
                ScriptFile(beat.script_name, self._join(list(beat.beat.commands)))
            )

        files.extend(self._chase_files(plan))

        if handover and schedule:
            files.append(
                ScriptFile(HANDOVER_SCRIPT_NAME, self._handover_script(schedule[0]))
            )

        return ScriptBundle(
            files=tuple(files),
            entry_script=SESSION_SCRIPT_NAME,
            handover_script=HANDOVER_SCRIPT_NAME if handover and schedule else "",
            listen_script=LISTEN_SCRIPT_NAME if self._recording.keep_game_open else "",
        )

    def _chase_files(self, plan: RecordingPlan) -> list[ScriptFile]:
        files: list[ScriptFile] = []
        for clip in plan.clips:
            if not clip.camera_path.is_usable:
                continue
            files.append(
                ScriptFile(
                    name=self._campath_name(clip),
                    content=CampathDocument.render(clip.camera_path),
                    extension=CAMPATH_EXTENSION,
                )
            )
            files.append(
                ScriptFile(self._flycam_name(clip), self._flycam_script(clip))
            )
        return files

    def _flycam_script(self, clip: ClipSpec) -> str:
        document = self._script_directory / f"{self._campath_name(clip)}{CAMPATH_EXTENSION}"
        return self._join(
            [
                "mirv_campath clear",
                f'mirv_campath load "{self._as_engine_path(document)}"',
                "mirv_campath offset current#0",
                "mirv_campath enabled 1",
            ]
        )

    @staticmethod
    def _campath_name(clip: ClipSpec) -> str:
        return f"highlighter_c{clip.index:02d}{CAMPATH_SUFFIX}"

    @staticmethod
    def _flycam_name(clip: ClipSpec) -> str:
        return f"highlighter_c{clip.index:02d}{FLY_SUFFIX}"

    @staticmethod
    def _chase_clips(plan: RecordingPlan) -> list[ClipSpec]:
        return [clip for clip in plan.clips if clip.camera_path.is_usable]

    @staticmethod
    def _beats(plan: RecordingPlan) -> list[ScheduledBeat]:
        return [
            ScheduledBeat(clip=clip, beat=beat)
            for clip in plan.clips
            for beat in clip.beats
        ]

    @staticmethod
    def _flatten(plan: RecordingPlan) -> list[ScheduledSegment]:
        return [
            ScheduledSegment(clip=clip, segment=segment)
            for clip in plan.clips
            for segment in clip.segments
        ]

    def _session_script(self, plan: RecordingPlan, schedule: list[ScheduledSegment]) -> str:
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

        for beat in self._beats(plan):
            lines.append(f"mirv_cmd addAtTick {beat.beat.tick} exec {beat.script_name}")

        for clip in self._chase_clips(plan):
            lines.append(
                f"mirv_cmd addAtTick {clip.camera_path.start_tick} "
                f"exec {self._flycam_name(clip)}"
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
                *self._camera_setup(entry),
                f'mirv_streams record name "{self._as_engine_path(take_path)}"',
                "mirv_streams record start",
            ]
        )

    def _camera_setup(self, entry: ScheduledSegment) -> list[str]:
        if entry.segment.setup_commands:
            return list(entry.segment.setup_commands)
        return [
            *self._spectate_commands(entry.clip),
            f"spec_mode {self._spectator_mode()}",
        ]

    def _end_script(
        self,
        plan: RecordingPlan,
        entry: ScheduledSegment,
        following: ScheduledSegment | None,
    ) -> str:
        lines = ["mirv_streams record end"]
        if entry.clip.camera_path.is_usable:
            lines.extend(["mirv_campath enabled 0", "mirv_campath clear"])
        if following is not None:
            if self._recording.skip_dead_time:
                lines.append(self._forward_seek(entry.segment.end_tick, following))
            return self._join(lines)
        return self._join(lines + self._finale(plan, entry))

    def _finale(self, plan: RecordingPlan, entry: ScheduledSegment) -> list[str]:
        if self._recording.keep_game_open:
            return [f"exec {FINISH_SCRIPT_NAME}"]
        if self._recording.close_game_when_done:
            quit_tick = entry.segment.end_tick + self._ticks(plan, QUIT_DELAY_SECONDS)
            return [f"mirv_cmd addAtTick {quit_tick} quit"]
        return []

    @classmethod
    def park_script(cls) -> str:
        return cls._join(
            [
                "mirv_cmd clear",
                f"exec {LISTEN_SCRIPT_NAME}",
                f"demo_gototick {BOOTSTRAP_TICK}",
            ]
        )

    @classmethod
    def disconnect_script(cls) -> str:
        return cls._join(["mirv_cmd clear", "disconnect"])

    def _listen_script(self, plan: RecordingPlan) -> str:
        first = BOOTSTRAP_TICK + self._ticks(plan, LISTEN_START_DELAY_SECONDS)
        last = self._listen_end_tick(plan)
        step = self._listen_step(plan, first, last)
        ticks = list(range(first, max(last, first + step), step))[:MAXIMUM_LISTEN_ENTRIES]
        return self._join(
            [f"mirv_cmd addAtTick {tick} exec {HANDOVER_SCRIPT_NAME}" for tick in ticks]
        )

    def _listen_step(self, plan: RecordingPlan, first: int, last: int) -> int:
        step = max(1, self._ticks(plan, self._recording.handover_interval_seconds))
        entries = max(1, (last - first) // step)
        if entries <= MAXIMUM_LISTEN_ENTRIES:
            return step
        return max(step, (last - first) // MAXIMUM_LISTEN_ENTRIES)

    def _listen_end_tick(self, plan: RecordingPlan) -> int:
        fallback = BOOTSTRAP_TICK + self._ticks(plan, FALLBACK_LISTEN_SECONDS)
        return max(plan.demo_end_tick, fallback)

    @staticmethod
    def _ticks(plan: RecordingPlan, seconds: float) -> int:
        return max(1, int(round(seconds * plan.tick_rate)))

    def _handover_script(self, first: ScheduledSegment) -> str:
        destination = max(0, first.segment.start_tick - self._recording.seek_lead_ticks)
        return self._join(
            [f"exec {SESSION_SCRIPT_NAME}", f"demo_gototick {destination}"]
        )

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
