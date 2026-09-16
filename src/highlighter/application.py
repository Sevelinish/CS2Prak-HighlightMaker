from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from .config.repository import ConfigRepository
from .config.schema import CONFIG_VERSION, ApplicationConfig
from .demo.locator import DemoLocator
from .demo.grenade_reader import GrenadeReader
from .demo.reader import DemoReader
from .detection.engine import HighlightEngine
from .detection.player_filter import PlayerResolver
from .domain.grenade import Grenade
from .domain.highlight import Highlight
from .domain.match import Match
from .domain.player import Player
from .game.installation import Cs2Installation
from .infrastructure.errors import HighlighterError
from .infrastructure.logging import LoggingConfigurator
from .infrastructure.paths import ApplicationPaths
from .media.assembler import AssembledClip
from .media.folder_opener import FolderOpener
from .media.reel import Reel
from .modes import RunMode
from .plan.builder import RecordingPlanBuilder
from .plan.nade_builder import NadePlanBuilder
from .plan.models import RecordingPlan
from .plan.writer import RecordingPlanWriter
from .presentation.banner import Banner
from .presentation.demo_picker import DemoPicker
from .presentation.grenade_table import GrenadeTable
from .presentation.highlight_table import HighlightTable
from .presentation.selector import HighlightSelector
from .presentation.steps import StepReporter
from .presentation.summary import RunSummary
from .presentation.theme import build_console
from .provisioning.toolchain import ToolchainProvisioner
from .recording.session import RecordingSession
from .recording.warm_session import WarmSession
from .update.service import UpdateService

BASE_STEPS = 7
PLAYER_LOOKUP_STEP = 1
EXIT_SUCCESS = 0
EXIT_FAILURE = 1


class Application:
    def __init__(
        self,
        demo_argument: str | None = None,
        player_query: str | None = None,
        mode_token: str | None = None,
        one_file: bool = False,
        keep_game_open: bool = False,
        fly: bool = False,
        verbose: bool = False,
    ) -> None:
        self._paths = ApplicationPaths.discover()
        self._console: Console = build_console()
        self._demo_argument = demo_argument
        self._player_query = player_query
        self._mode = RunMode.parse(mode_token)
        self._one_file = one_file
        self._keep_game_open = keep_game_open
        self._fly = fly
        self._verbose = verbose
        self._logger = LoggingConfigurator(self._paths.logs, verbose).configure()
        self._warm_session: WarmSession | None = None

    def run(self) -> int:
        self._console.print(Banner.build())
        try:
            return self._execute()
        except HighlighterError as error:
            self._console.print()
            self._console.print(
                Panel(
                    f"[danger]{error}[/danger]",
                    title="[danger]Stopped[/danger]",
                    title_align="left",
                    border_style="danger",
                    padding=(0, 2),
                    expand=False,
                )
            )
            self._logger.debug("Aborted", exc_info=True)
            return EXIT_FAILURE
        except KeyboardInterrupt:
            self._console.print("\n[warning]Cancelled[/warning]")
            return EXIT_FAILURE

    def _execute(self) -> int:
        repository = ConfigRepository(self._paths.config_file)
        config = repository.load()
        self._apply_debug_setting(config)
        UpdateService(self._console, self._paths, config).announce_installed()
        if self._one_file:
            config.recording.single_file = True
        if self._keep_game_open:
            config.recording.keep_game_open = True
        if self._fly:
            config.nades.follow_flight = True
        if repository.migrated:
            self._console.print(
                f"[muted]config.json upgraded to version {CONFIG_VERSION}[/muted]"
            )
        if self._fly and not self._mode.records_grenades:
            self._console.print(
                "[warning]-fly only applies to grenade modes, "
                "add -m nades or -m nades_smoke[/warning]"
            )

        installation = Cs2Installation.discover(config.paths.cs2_directory)
        reporter = StepReporter(self._console, self._total_steps())

        demo_path = self._resolve_demo(config, installation)
        if demo_path is None:
            self._console.print("[warning]No demo selected[/warning]")
            return EXIT_SUCCESS

        match = self._read_demo(demo_path, config, reporter)
        target = self._resolve_player(match, reporter)

        if self._mode.records_grenades:
            plan = self._grenade_plan(match, config, target, reporter)
        else:
            plan = self._highlight_plan(match, config, target, reporter)
        if plan is None:
            return EXIT_SUCCESS
        assembled, reel = self._record(plan, config, installation, reporter)
        self._open_folder(plan, assembled, config, reporter)
        self._report(assembled, plan, reel)
        return EXIT_SUCCESS

    def _apply_debug_setting(self, config: ApplicationConfig) -> None:
        if self._verbose or not config.debug:
            return
        self._logger = LoggingConfigurator(self._paths.logs, verbose=True).configure()
        self._logger.debug("Debug output enabled by config.json")

    def _total_steps(self) -> int:
        return BASE_STEPS + (PLAYER_LOOKUP_STEP if self._player_query else 0)

    def _resolve_demo(
        self, config: ApplicationConfig, installation: Cs2Installation
    ) -> Path | None:
        locator = self._build_locator(config, installation)
        if self._demo_argument:
            return self._named_demo(locator)

        demos = locator.discover()
        if not demos:
            raise HighlighterError(
                f"No .dem files found. Put demos in "
                f"{self._paths.resolve(config.paths.demo_directory)}"
            )
        return DemoPicker(self._console).pick(demos)

    def _build_locator(
        self, config: ApplicationConfig, installation: Cs2Installation
    ) -> DemoLocator:
        directories = [self._paths.resolve(config.paths.demo_directory)]
        directories.extend(installation.demo_directories())
        return DemoLocator(directories)

    def _named_demo(self, locator: DemoLocator) -> Path:
        given = self._demo_argument or ""
        direct = self._paths.resolve(given)
        if DemoLocator.is_demo(direct):
            return direct

        found = locator.find_by_name(Path(given).name)
        if found is not None:
            return found

        searched = "\n  ".join(str(folder) for folder in locator.search_directories)
        raise HighlighterError(
            f"No demo called '{given}'. Looked next to the exe and in:\n  {searched}"
        )

    def _highlight_plan(
        self,
        match: Match,
        config: ApplicationConfig,
        target: Player | None,
        reporter: StepReporter,
    ) -> RecordingPlan | None:
        highlights = self._detect(match, config, target, reporter)
        if not highlights:
            self._console.print(
                "[warning]Nothing passed the score threshold. "
                "Lower detection.minimumScore in config.json.[/warning]"
            )
            return None

        HighlightTable(self._console, match).render(highlights)
        selected = HighlightSelector(self._console).select(highlights)
        if not selected:
            self._console.print("[warning]Nothing selected[/warning]")
            return None
        return self._build_plan(match, selected, config, reporter)

    def _grenade_plan(
        self,
        match: Match,
        config: ApplicationConfig,
        target: Player | None,
        reporter: StepReporter,
    ) -> RecordingPlan | None:
        grenades = self._read_grenades(match, config, target, reporter)
        if not grenades:
            self._console.print(
                f"[warning]No {self._mode.label} found in this demo[/warning]"
            )
            return None

        GrenadeTable(self._console, match).render(grenades)
        selected = HighlightSelector(self._console).select(grenades)
        if not selected:
            self._console.print("[warning]Nothing selected[/warning]")
            return None

        reporter.begin("Planning grenade shots")
        output_root = self._paths.resolve(config.paths.output_directory)
        plan = NadePlanBuilder(config.recording, config.nades).build(
            match, selected, output_root
        )
        self._report_merges(reporter, plan, "throws")
        work_directory = self._paths.resolve(config.paths.work_directory)
        plan_file = RecordingPlanWriter(work_directory / "plans").write(plan)
        reporter.detail(str(plan_file))
        reporter.done(f"{plan.clip_count} shots, {plan.total_seconds:.0f}s of footage")
        return plan

    def _read_grenades(
        self,
        match: Match,
        config: ApplicationConfig,
        target: Player | None,
        reporter: StepReporter,
    ) -> list[Grenade]:
        reporter.begin(f"Scanning for {self._mode.label} grenades")
        try:
            grenades = GrenadeReader(
                match.demo_path, match, config.nades.callout_sample_stride
            ).read(self._mode.grenade_kinds)
        except BaseException:
            reporter.fail()
            raise

        if target is not None:
            grenades = [
                item for item in grenades if item.thrower.steam_id64 == target.steam_id64
            ]

        places = len({item.landing_place for item in grenades})
        reporter.done(f"{len(grenades)} found across {places} spot(s)")
        return grenades

    def _read_demo(
        self, demo_path: Path, config: ApplicationConfig, reporter: StepReporter
    ) -> Match:
        reporter.begin(f"Reading {demo_path.name}")
        try:
            match = DemoReader(demo_path, config.game.tick_rate).read()
        except BaseException:
            reporter.fail()
            raise
        reporter.done(
            f"{match.map_name}, {match.round_count} rounds, {len(match.players)} players"
        )
        return match

    def _resolve_player(self, match: Match, reporter: StepReporter) -> Player | None:
        if not self._player_query:
            return None

        reporter.begin(f"Looking up '{self._player_query}'")
        try:
            player = PlayerResolver(match).resolve(self._player_query)
        except BaseException:
            reporter.fail()
            raise
        reporter.done(f"{player.name} (slot {player.slot})")
        return player

    def _detect(
        self,
        match: Match,
        config: ApplicationConfig,
        target: Player | None,
        reporter: StepReporter,
    ) -> list[Highlight]:
        scope = f" for {target.name}" if target is not None else ""
        reporter.begin(f"Scanning for highlights{scope}")
        try:
            highlights = HighlightEngine(config.detection).detect(
                match, target.steam_id64 if target is not None else None
            )
        except BaseException:
            reporter.fail()
            raise
        reporter.done(f"{len(highlights)} found")
        return highlights

    def _build_plan(
        self,
        match: Match,
        selected: list[Highlight],
        config: ApplicationConfig,
        reporter: StepReporter,
    ) -> RecordingPlan:
        reporter.begin("Planning clips")
        output_root = self._paths.resolve(config.paths.output_directory)
        plan = RecordingPlanBuilder(config.recording).build(match, selected, output_root)
        self._report_merges(reporter, plan, "moments")

        work_directory = self._paths.resolve(config.paths.work_directory)
        plan_file = RecordingPlanWriter(work_directory / "plans").write(plan)
        reporter.detail(str(plan_file))
        reporter.done(
            f"{plan.clip_count} clips, "
            f"{sum(len(clip.segments) for clip in plan.clips)} segments, "
            f"{plan.total_seconds:.0f}s of footage"
        )
        return plan

    @staticmethod
    def _report_merges(reporter: StepReporter, plan: RecordingPlan, label: str) -> None:
        if plan.merged_sources <= 0:
            return
        reporter.detail(
            f"{plan.merged_sources} overlapping {label} folded into the clip they share"
        )

    def _record(
        self,
        plan: RecordingPlan,
        config: ApplicationConfig,
        installation: Cs2Installation,
        reporter: StepReporter,
    ) -> tuple[list[AssembledClip], Reel | None]:
        tools_directory = self._paths.resolve(config.paths.tools_directory)
        toolchain = ToolchainProvisioner(
            self._console,
            config.paths,
            config.toolchain,
            tools_directory,
            config.game.hook_dll_relative_path,
        ).provision()

        session = RecordingSession(
            console=self._console,
            config=config,
            installation=installation,
            toolchain=toolchain,
            work_directory=self._paths.resolve(config.paths.work_directory),
            output_root=self._paths.resolve(config.paths.output_directory),
        )
        assembled = session.execute(plan, reporter)
        self._warm_session = session.warm_session
        return assembled, session.reel

    def _open_folder(
        self,
        plan: RecordingPlan,
        assembled: list[AssembledClip],
        config: ApplicationConfig,
        reporter: StepReporter,
    ) -> None:
        reporter.begin("Opening the output folder")
        if not assembled:
            reporter.done("skipped, nothing was written")
            return

        folder = plan.output_directory / plan.demo_name
        opened = FolderOpener(config.recording.open_output_folder).open(folder)
        reporter.done(str(folder) if opened else f"not opened: {folder}")

    def _report(
        self,
        assembled: list[AssembledClip],
        plan: RecordingPlan,
        reel: Reel | None = None,
    ) -> None:
        RunSummary(self._console).render(assembled, plan, reel, self._warm_session)
