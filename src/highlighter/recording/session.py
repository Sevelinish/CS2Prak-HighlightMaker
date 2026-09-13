from __future__ import annotations

import shutil
from pathlib import Path

from rich.console import Console

from ..config.schema import ApplicationConfig
from ..game.installation import Cs2Installation
from ..infrastructure.logging import get_logger
from ..media.assembler import AssembledClip, ClipAssembler
from ..media.crosshair import CrosshairFilterBuilder
from ..media.encoders import EncoderProfile, EncoderSelector
from ..media.output_library import OutputLibrary
from ..media.reel import Reel, ReelBuilder
from ..plan.models import RecordingPlan
from ..presentation.steps import StepReporter
from ..provisioning.hlae_installation import HlaeInstallation
from ..provisioning.toolchain import Toolchain
from .graphics import GraphicsProfile
from .launcher import HlaeLauncher
from .mirv_script import MirvScriptBuilder
from .script_writer import ScriptWriter

SECONDS_PER_MINUTE = 60
VIDEO_SUFFIX = ".mp4"
PROGRESS_INTERVAL_SECONDS = 30


class RecordingSession:
    def __init__(
        self,
        console: Console,
        config: ApplicationConfig,
        installation: Cs2Installation,
        toolchain: Toolchain,
        work_directory: Path,
        output_root: Path,
    ) -> None:
        self._console = console
        self._config = config
        self._installation = installation
        self._toolchain = toolchain
        self._work_directory = work_directory
        self._output_root = output_root
        self._reel: Reel | None = None
        self._logger = get_logger("recording")

    @property
    def reel(self) -> Reel | None:
        return self._reel

    def execute(self, plan: RecordingPlan, reporter: StepReporter) -> list[AssembledClip]:
        take_directory = self._prepare_take_directory(plan)
        script_writer = ScriptWriter(
            self._installation.config_directory, self._work_directory / "scripts"
        )
        graphics = GraphicsProfile(self._installation, self._config.recording, self._config.game)
        encoder = EncoderSelector(self._toolchain.ffmpeg, self._config.encoding).select()

        bundle = MirvScriptBuilder(
            self._config.recording, encoder, self._config.game, take_directory
        ).build(plan)

        try:
            script_writer.write(bundle)
            graphics.apply()
            self._run_game(plan, bundle.entry_script, take_directory, reporter, encoder)
        finally:
            graphics.restore()
            script_writer.cleanup()

        return self._save(plan, take_directory, encoder, reporter)

    def _run_game(
        self,
        plan: RecordingPlan,
        entry_script: str,
        take_directory: Path,
        reporter: StepReporter,
        encoder: EncoderProfile,
    ) -> None:
        hlae = HlaeInstallation(self._toolchain.hlae, self._config.game.hook_dll_relative_path)
        hlae.register_ffmpeg(self._toolchain.ffmpeg)

        launcher = HlaeLauncher(
            hlae=hlae,
            installation=self._installation,
            recording=self._config.recording,
            game=self._config.game,
            steam_root=self._installation.steam_root,
        )

        reporter.begin("Launching Counter-Strike 2")
        reporter.detail(
            f"encoder {encoder.codec}{' (hardware)' if encoder.is_hardware else ''}"
        )
        reporter.detail("HLAE injects the hook, then hands the game over")
        started = False

        def on_launched() -> None:
            nonlocal started
            reporter.done("game is up")
            reporter.begin(
                f"Recording {plan.clip_count} clip(s) in "
                f"{self._segment_total(plan)} segment(s)"
            )
            reporter.detail("the game closes itself after the last clip")
            started = True

        try:
            launcher.run(
                entry_script,
                plan.demo_path,
                on_launched=on_launched,
                on_progress=lambda elapsed: self._report_progress(
                    reporter, started, plan, take_directory, elapsed
                ),
            )
        except BaseException:
            reporter.fail()
            raise

        reporter.done(
            f"{self._count_recorded_clips(take_directory)} of {plan.clip_count} clips captured"
        )

    def _save(
        self,
        plan: RecordingPlan,
        take_directory: Path,
        encoder: EncoderProfile,
        reporter: StepReporter,
    ) -> list[AssembledClip]:
        reporter.begin("Saving videos")
        if self._config.crosshair.enabled:
            reporter.detail("drawing the crosshair overlay")

        library = self._build_library(plan)
        try:
            assembled = self._assemble(plan, take_directory, encoder, library)
            self._reel = self._join(assembled, library, reporter)
        except BaseException:
            reporter.fail()
            raise

        reporter.done(f"{len(assembled)} of {plan.clip_count} clips written")
        return assembled

    def _join(
        self, assembled: list[AssembledClip], library: OutputLibrary, reporter: StepReporter
    ) -> Reel | None:
        if not self._config.recording.single_file or not assembled:
            return None

        reporter.detail(f"joining {len(assembled)} clip(s) into one file")
        reel = ReelBuilder(self._toolchain.ffmpeg, library).build(assembled)
        if reel is not None:
            reporter.detail(reel.output.name)
        return reel

    def _build_library(self, plan: RecordingPlan) -> OutputLibrary:
        return OutputLibrary(
            self._output_root,
            plan.demo_name,
            self._config.encoding.container,
            single_file=self._config.recording.single_file,
        )

    def _report_progress(
        self,
        reporter: StepReporter,
        started: bool,
        plan: RecordingPlan,
        take_directory: Path,
        elapsed: float,
    ) -> None:
        if not started or elapsed < 1 or int(elapsed) % PROGRESS_INTERVAL_SECONDS != 0:
            return
        minutes, seconds = divmod(int(elapsed), SECONDS_PER_MINUTE)
        reporter.detail(
            f"{self._count_recorded_clips(take_directory)}/{plan.clip_count} clips, "
            f"elapsed {minutes:02d}:{seconds:02d}"
        )

    @staticmethod
    def _count_recorded_clips(take_directory: Path) -> int:
        if not take_directory.is_dir():
            return 0
        return sum(
            1
            for clip_directory in take_directory.iterdir()
            if clip_directory.is_dir() and any(clip_directory.rglob(f"*{VIDEO_SUFFIX}"))
        )

    @staticmethod
    def _segment_total(plan: RecordingPlan) -> int:
        return sum(len(clip.segments) for clip in plan.clips)

    def _assemble(
        self,
        plan: RecordingPlan,
        take_directory: Path,
        encoder: EncoderProfile,
        library: OutputLibrary,
    ) -> list[AssembledClip]:
        assembler = ClipAssembler(
            ffmpeg_executable=self._toolchain.ffmpeg,
            encoding=self._config.encoding,
            encoder=encoder,
            take_directory=take_directory,
            library=library,
            video_filter=CrosshairFilterBuilder(self._config.crosshair).build(),
        )
        return assembler.assemble(plan)

    def _prepare_take_directory(self, plan: RecordingPlan) -> Path:
        take_directory = self._work_directory / "takes" / plan.demo_name
        if take_directory.exists():
            shutil.rmtree(take_directory, ignore_errors=True)
        take_directory.mkdir(parents=True, exist_ok=True)
        return take_directory
