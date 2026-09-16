from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Callable

from rich.console import Console

from ..config.schema import ApplicationConfig
from ..game.installation import Cs2Installation
from ..infrastructure.logging import get_logger
from ..infrastructure.progress import ProgressReporter
from ..media.assembler import AssembledClip, ClipAssembler
from ..media.crosshair import CrosshairFilterBuilder
from ..media.encoders import EncoderProfile, EncoderSelector
from ..media.output_library import OutputLibrary
from ..media.reel import Reel, ReelBuilder
from ..plan.models import RecordingPlan
from ..provisioning.hlae_installation import HlaeInstallation
from ..provisioning.toolchain import Toolchain
from .game_process import GameProcessWatcher
from .graphics import GraphicsProfile
from .launcher import HlaeLauncher
from .mirv_script import (
    FINISH_SCRIPT_NAME,
    HANDOVER_SCRIPT_NAME,
    MirvScriptBuilder,
    ScriptBundle,
)
from .netcon import NetconClient, NetconEndpoint
from .script_writer import ScriptWriter
from .take_watcher import TakeProgress, TakeWatcher
from .warm_session import (
    DEMO_CHANNEL,
    NETCON_CHANNEL,
    WarmSession,
    WarmSessionStore,
)

SECONDS_PER_MINUTE = 60
VIDEO_SUFFIX = ".mp4"
PROGRESS_INTERVAL_SECONDS = 30
SHUTDOWN_GRACE_SECONDS = 10.0
SHUTDOWN_POLL_SECONDS = 0.5
NETCON_PROBE_SECONDS = 60.0
GAME_CLOSE_GRACE_SECONDS = 60.0


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
        self._store = WarmSessionStore(work_directory)
        self._reel: Reel | None = None
        self._warm_session: WarmSession | None = None
        self._reused_game = False
        self._netcon: NetconEndpoint | None = None
        self._channel = DEMO_CHANNEL
        self._logger = get_logger("recording")

    @property
    def reel(self) -> Reel | None:
        return self._reel

    @property
    def warm_session(self) -> WarmSession | None:
        return self._warm_session

    @property
    def reused_game(self) -> bool:
        return self._reused_game

    def execute(self, plan: RecordingPlan, reporter: ProgressReporter) -> list[AssembledClip]:
        take_directory = self._prepare_take_directory(plan)
        script_writer = ScriptWriter(
            self._installation.config_directory, self._work_directory / "scripts"
        )
        graphics = GraphicsProfile(
            self._installation,
            self._config.recording,
            self._config.game,
            self._work_directory,
        )
        encoder = EncoderSelector(self._toolchain.ffmpeg, self._config.encoding).select()
        watcher = TakeWatcher(
            plan,
            take_directory,
            self._config.recording.take_settle_seconds,
            self._config.recording.take_stall_seconds,
        )

        try:
            self._play(plan, take_directory, encoder, watcher, script_writer, graphics, reporter)
        finally:
            self._settle(plan, graphics, script_writer)

        return self._save(plan, take_directory, encoder, reporter)

    def _play(
        self,
        plan: RecordingPlan,
        take_directory: Path,
        encoder: EncoderProfile,
        watcher: TakeWatcher,
        script_writer: ScriptWriter,
        graphics: GraphicsProfile,
        reporter: ProgressReporter,
    ) -> None:
        reporter.begin("Starting Counter-Strike 2")
        reporter.detail(
            f"encoder {encoder.codec}{' (hardware)' if encoder.is_hardware else ''}"
        )

        warm = self._store.usable_for(plan, self._config.recording)
        if warm is not None and self._try_handover(
            plan, take_directory, encoder, watcher, script_writer, reporter, warm
        ):
            return

        bundle = self._bundle(plan, take_directory, encoder, handover=False)
        script_writer.write(bundle)
        graphics.apply()
        self._launch(plan, bundle, watcher, script_writer, reporter)

    def _try_handover(
        self,
        plan: RecordingPlan,
        take_directory: Path,
        encoder: EncoderProfile,
        watcher: TakeWatcher,
        script_writer: ScriptWriter,
        reporter: ProgressReporter,
        warm: WarmSession,
    ) -> bool:
        bundle = self._bundle(plan, take_directory, encoder, handover=not warm.uses_netcon)
        script_writer.write(bundle)
        reporter.detail(
            f"reusing the running game, pid {warm.pid}, "
            f"{warm.seconds_left:.0f}s of warm time left"
        )

        if not self._wake(plan, bundle, warm, script_writer, reporter):
            self._abandon(warm)
            return False

        if not watcher.wait_for_start(
            self._config.recording.handover_timeout_seconds, warm.is_running
        ):
            reporter.detail("the running game did not answer, launching a fresh one")
            self._abandon(warm)
            return False

        script_writer.drop(HANDOVER_SCRIPT_NAME)
        self._reused_game = True
        reporter.done("handed to the running game, no restart")
        self._capture(plan, watcher, reporter, warm.is_running)
        return True

    def _wake(
        self,
        plan: RecordingPlan,
        bundle: ScriptBundle,
        warm: WarmSession,
        script_writer: ScriptWriter,
        reporter: ProgressReporter,
    ) -> bool:
        if not warm.uses_netcon:
            reporter.detail("the running demo will pick the new script up")
            return True

        self._netcon = warm.endpoint
        self._channel = NETCON_CHANNEL
        if self._config.recording.keep_game_open:
            script_writer.replace(FINISH_SCRIPT_NAME, MirvScriptBuilder.disconnect_script())

        reporter.detail(f"telling the game console on 127.0.0.1:{warm.netcon_port} to play it")
        sent = NetconClient(warm.endpoint).send(
            [
                f"exec {bundle.entry_script}",
                f'playdemo "{plan.demo_path}"',
            ]
        )
        if not sent:
            reporter.detail("the game console did not answer, launching a fresh one")
        return sent

    def _launch(
        self,
        plan: RecordingPlan,
        bundle: ScriptBundle,
        watcher: TakeWatcher,
        script_writer: ScriptWriter,
        reporter: ProgressReporter,
    ) -> None:
        self._netcon = self._wanted_netcon()
        launcher = self._launcher(self._netcon)
        reporter.detail("HLAE injects the hook, then hands the game over")
        try:
            launcher.start(bundle.entry_script, plan.demo_path)
        except BaseException:
            reporter.fail()
            raise

        self._settle_channel(script_writer, reporter)
        reporter.done("game is up")
        self._capture(plan, watcher, reporter, launcher.is_running)

    def _wanted_netcon(self) -> NetconEndpoint | None:
        recording = self._config.recording
        if not recording.keep_game_open or recording.handover_channel != NETCON_CHANNEL:
            return None
        return NetconEndpoint.create(self._config.game.netcon_port)

    def _settle_channel(self, script_writer: ScriptWriter, reporter: ProgressReporter) -> None:
        if not self._config.recording.keep_game_open:
            return

        self._channel = DEMO_CHANNEL
        if self._netcon is None:
            reporter.detail("the demo will keep playing so the next batch can be handed over")
            return

        reporter.detail(f"game console on 127.0.0.1:{self._netcon.port}")
        if NetconClient(self._netcon).wait_until_reachable(NETCON_PROBE_SECONDS):
            self._channel = NETCON_CHANNEL
            script_writer.replace(FINISH_SCRIPT_NAME, MirvScriptBuilder.disconnect_script())
            reporter.detail("the demo will close and the game will wait on the main menu")
            return

        self._netcon = None
        reporter.detail("no console port, the demo will keep playing instead")
        self._logger.warning(
            "This CS2 build did not open a console port, falling back to the demo channel"
        )

    def _launcher(self, netcon: NetconEndpoint | None = None) -> HlaeLauncher:
        hlae = HlaeInstallation(self._toolchain.hlae, self._config.game.hook_dll_relative_path)
        hlae.register_ffmpeg(self._toolchain.ffmpeg)
        return HlaeLauncher(
            hlae=hlae,
            installation=self._installation,
            recording=self._config.recording,
            game=self._config.game,
            steam_root=self._installation.steam_root,
            netcon=netcon,
        )

    def _bundle(
        self,
        plan: RecordingPlan,
        take_directory: Path,
        encoder: EncoderProfile,
        handover: bool,
    ) -> ScriptBundle:
        return MirvScriptBuilder(
            self._config.recording,
            encoder,
            self._config.game,
            take_directory,
            self._installation.config_directory,
        ).build(plan, handover=handover)

    def _capture(
        self,
        plan: RecordingPlan,
        watcher: TakeWatcher,
        reporter: ProgressReporter,
        is_alive: Callable[[], bool],
    ) -> None:
        reporter.begin(
            f"Recording {plan.clip_count} clip(s) in {self._segment_total(plan)} segment(s)"
        )
        if self._config.recording.keep_game_open:
            reporter.detail("the game stays open so the next batch skips the startup")
        else:
            reporter.detail("the game closes itself once the takes are written")

        timeout = self._config.game.recording_timeout_minutes * SECONDS_PER_MINUTE
        try:
            watcher.wait(
                timeout_seconds=timeout,
                on_progress=lambda progress: self._report_progress(reporter, progress),
                is_alive=is_alive,
            )
            self._close_game(reporter)
        except BaseException:
            reporter.fail()
            raise

        captured = watcher.snapshot().completed
        reporter.done(f"{captured} of {watcher.segment_count} segment(s) captured")

    def _close_game(self, reporter: ProgressReporter) -> None:
        recording = self._config.recording
        if recording.keep_game_open or not recording.close_game_when_done:
            return

        processes = GameProcessWatcher(self._installation.executable.name)
        if not processes.is_running():
            return

        reporter.detail("closing the game")
        if processes.wait_until_stopped(GAME_CLOSE_GRACE_SECONDS):
            return

        self._logger.warning("The game did not close on its own, stopping it")
        processes.terminate()
        processes.wait_until_stopped(SHUTDOWN_GRACE_SECONDS)

    def _abandon(self, warm: WarmSession) -> None:
        self._logger.warning(
            "Warm session pid %d did not pick the script up, closing it", warm.pid
        )
        watcher = GameProcessWatcher(warm.executable)
        watcher.terminate()
        self._store.clear()

        deadline = time.monotonic() + SHUTDOWN_GRACE_SECONDS
        while watcher.is_running() and time.monotonic() < deadline:
            time.sleep(SHUTDOWN_POLL_SECONDS)

    def _settle(
        self, plan: RecordingPlan, graphics: GraphicsProfile, script_writer: ScriptWriter
    ) -> None:
        recording = self._config.recording
        if recording.keep_game_open and self._game_is_running():
            script_writer.drop(HANDOVER_SCRIPT_NAME)
            self._warm_session = self._store.remember(
                plan,
                recording,
                self._installation.executable.name,
                self._installation.config_directory,
                HANDOVER_SCRIPT_NAME,
                graphics_restore_pending=self._config.game.restore_graphics_on_exit,
                channel=self._channel,
                netcon=self._netcon,
            )
            if self._warm_session is not None:
                self._logger.info(
                    "Game left running, warm for %.0fs", self._warm_session.seconds_left
                )
            return

        graphics.restore()
        script_writer.cleanup()
        self._store.clear()

    def _game_is_running(self) -> bool:
        try:
            return GameProcessWatcher(self._installation.executable.name).is_running()
        except OSError:
            return False

    def _save(
        self,
        plan: RecordingPlan,
        take_directory: Path,
        encoder: EncoderProfile,
        reporter: ProgressReporter,
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
        self,
        assembled: list[AssembledClip],
        library: OutputLibrary,
        reporter: ProgressReporter,
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

    @staticmethod
    def _report_progress(reporter: ProgressReporter, progress: TakeProgress) -> None:
        if progress.elapsed_seconds < 1:
            return
        if int(progress.elapsed_seconds) % PROGRESS_INTERVAL_SECONDS != 0:
            return
        minutes, seconds = divmod(int(progress.elapsed_seconds), SECONDS_PER_MINUTE)
        reporter.detail(
            f"{progress.completed}/{progress.total} segments, "
            f"elapsed {minutes:02d}:{seconds:02d}"
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
