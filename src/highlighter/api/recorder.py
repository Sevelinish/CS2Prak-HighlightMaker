from __future__ import annotations

from pathlib import Path

from rich.console import Console

from ..config.schema import ApplicationConfig
from ..domain.grenade import GrenadeKind
from ..game.installation import Cs2Installation
from ..media.assembler import AssembledClip
from ..media.folder_opener import FolderOpener
from ..media.reel import Reel
from ..plan.builder import RecordingPlanBuilder
from ..plan.models import RecordingPlan
from ..plan.nade_builder import NadePlanBuilder
from ..plan.writer import RecordingPlanWriter
from ..provisioning.toolchain import ToolchainProvisioner
from ..recording.game_process import GameProcessWatcher
from ..recording.session import RecordingSession
from .configuration import ConfigMerger
from .errors import ApiError, ErrorCode
from .events import EventType
from .jobs import JobArtifact, JobRecord, JobResult, JobStageTracker, SourceKind
from .selection import GrenadeSelection, HighlightSelection
from .serialization import PlanView
from .workspace import DemoWorkspace

CLIP_ARTIFACT = "clip"
REEL_ARTIFACT = "reel"
STAGE_TOTAL = 8


class RecordingJobExecutor:
    def __init__(self, workspace: DemoWorkspace) -> None:
        self._workspace = workspace
        self._console = Console(quiet=True)

    def execute(self, record: JobRecord, reporter) -> JobResult:
        tracker = JobStageTracker(record, reporter)
        config = ConfigMerger.apply(self._workspace.config, record.request.overrides)

        plan = self._plan(record, tracker, config)
        record.plan = PlanView.render(plan)
        tracker.publish(EventType.PLAN_READY, {"plan": record.plan})

        installation = self._installation(config)
        toolchain = self._provision(tracker, config)
        assembled, reel = self._record(record, tracker, config, plan, installation, toolchain)
        self._reveal(tracker, config, plan, assembled)
        return self._result(plan, assembled, reel)

    def _plan(
        self, record: JobRecord, tracker: JobStageTracker, config: ApplicationConfig
    ) -> RecordingPlan:
        demo_path = record.request.demo_path
        tracker.begin(f"Reading {demo_path.name}")
        match = self._workspace.match(demo_path)
        tracker.done(
            f"{match.map_name}, {match.round_count} rounds, {len(match.players)} players"
        )

        tracker.begin(f"Selecting {record.request.source.value}")
        output_root = self._workspace.paths.resolve(config.paths.output_directory)
        if record.request.source is SourceKind.GRENADES:
            plan = self._grenade_plan(record, tracker, config, demo_path, output_root)
        else:
            plan = self._highlight_plan(record, tracker, config, demo_path, output_root)

        tracker.begin("Planning clips")
        work_directory = self._workspace.paths.resolve(config.paths.work_directory)
        plan_file = RecordingPlanWriter(work_directory / "plans").write(plan)
        tracker.detail(str(plan_file))
        tracker.done(
            f"{plan.clip_count} clips, "
            f"{sum(len(clip.segments) for clip in plan.clips)} segments, "
            f"{plan.total_seconds:.0f}s of footage"
        )
        return plan

    def _highlight_plan(
        self,
        record: JobRecord,
        tracker: JobStageTracker,
        config: ApplicationConfig,
        demo_path: Path,
        output_root: Path,
    ) -> RecordingPlan:
        found = self._workspace.highlights(demo_path, config.detection)
        selected = HighlightSelection(record.request.criteria).apply(found)
        if not selected:
            tracker.fail("nothing matched")
            raise ApiError(
                ErrorCode.EMPTY_SELECTION,
                "No highlight matched the selection",
                {"available": len(found), "selection": record.request.criteria.to_mapping()},
            )
        tracker.done(f"{len(selected)} of {len(found)} highlights")
        return RecordingPlanBuilder(config.recording).build(
            self._workspace.match(demo_path), selected, output_root
        )

    def _grenade_plan(
        self,
        record: JobRecord,
        tracker: JobStageTracker,
        config: ApplicationConfig,
        demo_path: Path,
        output_root: Path,
    ) -> RecordingPlan:
        kinds = record.request.criteria.grenade_kinds or tuple(GrenadeKind)
        found = self._workspace.grenades(demo_path, kinds)
        selected = GrenadeSelection(record.request.criteria).apply(found)
        if not selected:
            tracker.fail("nothing matched")
            raise ApiError(
                ErrorCode.EMPTY_SELECTION,
                "No grenade matched the selection",
                {"available": len(found), "selection": record.request.criteria.to_mapping()},
            )
        tracker.done(f"{len(selected)} of {len(found)} grenades")
        return NadePlanBuilder(config.recording, config.nades).build(
            self._workspace.match(demo_path), selected, output_root
        )

    def _installation(self, config: ApplicationConfig) -> Cs2Installation:
        return Cs2Installation.discover(config.paths.cs2_directory)

    def _provision(self, tracker: JobStageTracker, config: ApplicationConfig):
        tracker.begin("Preparing HLAE and ffmpeg")
        tools_directory = self._workspace.paths.resolve(config.paths.tools_directory)
        toolchain = ToolchainProvisioner(
            self._console,
            config.paths,
            config.toolchain,
            tools_directory,
            config.game.hook_dll_relative_path,
        ).provision()
        tracker.done(f"{toolchain.hlae.name} and {toolchain.ffmpeg.name} ready")
        return toolchain

    def _record(
        self,
        record: JobRecord,
        tracker: JobStageTracker,
        config: ApplicationConfig,
        plan: RecordingPlan,
        installation: Cs2Installation,
        toolchain,
    ) -> tuple[list[AssembledClip], Reel | None]:
        watcher = GameProcessWatcher(installation.executable.name)
        record.cancellation.register(watcher.terminate)
        record.cancellation.raise_if_cancelled()

        session = RecordingSession(
            console=self._console,
            config=config,
            installation=installation,
            toolchain=toolchain,
            work_directory=self._workspace.paths.resolve(config.paths.work_directory),
            output_root=self._workspace.paths.resolve(config.paths.output_directory),
        )
        assembled = session.execute(plan, tracker)
        record.cancellation.raise_if_cancelled()

        for clip in assembled:
            tracker.publish(
                EventType.CLIP_WRITTEN,
                {
                    "name": clip.output.name,
                    "path": str(clip.output),
                    "segmentCount": clip.segment_count,
                    "hasAudio": clip.has_audio,
                },
            )
        return assembled, session.reel

    def _reveal(
        self,
        tracker: JobStageTracker,
        config: ApplicationConfig,
        plan: RecordingPlan,
        assembled: list[AssembledClip],
    ) -> None:
        tracker.begin("Opening the output folder")
        if not assembled:
            tracker.done("skipped, nothing was written")
            return
        folder = plan.output_directory / plan.demo_name
        opened = FolderOpener(config.recording.open_output_folder).open(folder)
        tracker.done(str(folder) if opened else f"not opened: {folder}")

    @staticmethod
    def _result(
        plan: RecordingPlan, assembled: list[AssembledClip], reel: Reel | None
    ) -> JobResult:
        return JobResult(
            output_directory=str(plan.output_directory / plan.demo_name),
            requested_clips=plan.clip_count,
            artifacts=[
                JobArtifact(
                    name=clip.output.name,
                    path=str(clip.output),
                    kind=CLIP_ARTIFACT,
                    duration_seconds=clip.clip.duration_seconds,
                    segment_count=clip.segment_count,
                    has_audio=clip.has_audio,
                )
                for clip in assembled
            ],
            reel=(
                JobArtifact(
                    name=reel.output.name,
                    path=str(reel.output),
                    kind=REEL_ARTIFACT,
                    duration_seconds=reel.duration_seconds,
                    segment_count=reel.clip_count,
                )
                if reel is not None
                else None
            ),
        )
