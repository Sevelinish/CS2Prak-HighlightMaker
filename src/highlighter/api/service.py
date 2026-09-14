from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Mapping

from ..config.repository import ConfigRepository
from ..domain.grenade import GrenadeKind
from ..media.folder_opener import FolderOpener
from ..plan.builder import RecordingPlanBuilder
from ..plan.models import RecordingPlan
from ..plan.nade_builder import NadePlanBuilder
from .configuration import ConfigMerger, ConfigSchema
from .contract import (
    CapabilityDescriptor,
    PLUGIN_NAME,
    PROTOCOL_VERSION,
    PluginDescriptor,
)
from .envelope import new_identifier
from .errors import ApiError, BadRequestError, ErrorCode
from .events import EventJournal
from .jobs import JobQueue, JobRequest, JobState, SourceKind
from .probe import SystemProbe
from .recorder import STAGE_TOTAL, RecordingJobExecutor
from .selection import GrenadeSelection, HighlightSelection, SelectionCriteria
from .serialization import (
    FileView,
    GrenadeView,
    HighlightView,
    MatchView,
    PlanView,
    PlayerView,
    RoundView,
)
from .workspace import DemoWorkspace

VIDEO_SUFFIXES = (".mp4", ".mkv", ".mov")
DEFAULT_EVENT_LIMIT = 200


class PluginService:
    def __init__(
        self,
        workspace: DemoWorkspace,
        repository: ConfigRepository,
        transports: tuple[str, ...] = (),
    ) -> None:
        self._workspace = workspace
        self._repository = repository
        self._transports = transports
        self._journal = EventJournal()
        self._executor = RecordingJobExecutor(workspace)
        self._jobs = JobQueue(self._run_job, self._journal, STAGE_TOTAL)
        self._shutdown = threading.Event()
        self._lock = threading.Lock()

    @property
    def journal(self) -> EventJournal:
        return self._journal

    @property
    def shutdown_requested(self) -> threading.Event:
        return self._shutdown

    def start(self) -> None:
        self._jobs.start()

    def stop(self) -> None:
        self._jobs.stop()

    def _run_job(self, record, reporter):
        return self._executor.execute(record, reporter)

    def handshake(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        requested = str(payload.get("protocol") or PROTOCOL_VERSION).strip()
        if requested.split(".")[0] != PROTOCOL_VERSION.split(".")[0]:
            raise ApiError(
                ErrorCode.UNSUPPORTED_PROTOCOL,
                f"{PLUGIN_NAME} speaks protocol {PROTOCOL_VERSION}, the client asked for "
                f"{requested}",
                {"supported": PROTOCOL_VERSION, "requested": requested},
            )

        config = self._workspace.config
        descriptor = PluginDescriptor(
            transports=self._transports,
            capabilities=self._capabilities(),
            root=str(self._workspace.paths.root),
            config_file=str(self._repository.config_file),
            output_directory=str(
                self._workspace.paths.resolve(config.paths.output_directory)
            ),
        )
        document = descriptor.to_mapping()
        document["client"] = {
            "name": str(payload.get("clientName") or ""),
            "version": str(payload.get("clientVersion") or ""),
        }
        return document

    def _capabilities(self) -> tuple[CapabilityDescriptor, ...]:
        return (
            CapabilityDescriptor("highlights", True, "Detect and record multi kill rounds"),
            CapabilityDescriptor("grenades", True, "Detect and record grenade throws"),
            CapabilityDescriptor(
                "grenadeCallouts", True, "Name the landing spot from the nav place names"
            ),
            CapabilityDescriptor("singleFile", True, "Join every clip into one video"),
            CapabilityDescriptor("perJobOverrides", True, "Override any setting for one job"),
            CapabilityDescriptor("jobQueue", True, "One recording runs at a time, the rest queue"),
            CapabilityDescriptor("eventStream", True, "Job events are readable and streamable"),
            CapabilityDescriptor(
                "cancellation", True, "Queued jobs stop instantly, running jobs close the game"
            ),
            CapabilityDescriptor("planPreview", True, "Inspect a plan before the game launches"),
            CapabilityDescriptor("autoDownload", True, "HLAE and ffmpeg install themselves"),
            CapabilityDescriptor(
                "concurrentRecording", False, "CS2 and HLAE allow only one recording at a time"
            ),
        )

    def probe(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return SystemProbe(self._workspace).report()

    def config_get(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "configFile": str(self._repository.config_file),
            "config": self._workspace.config.to_mapping(),
        }

    def config_describe(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return ConfigSchema.describe()

    def config_patch(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        patch = payload.get("patch")
        if patch is None:
            raise BadRequestError("config.patch needs a 'patch' object")

        with self._lock:
            updated = ConfigMerger.apply(self._workspace.config, patch)
            if bool(payload.get("persist", True)):
                self._repository.save(updated)
            self._workspace.adopt(updated)

        return {
            "configFile": str(self._repository.config_file),
            "persisted": bool(payload.get("persist", True)),
            "config": updated.to_mapping(),
        }

    def demos_list(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        search = str(payload.get("search") or "").strip().lower()
        limit = int(payload.get("limit") or 0)
        found = [
            path
            for path in self._workspace.demos()
            if not search or search in path.name.lower()
        ]
        limited = found[:limit] if limit > 0 else found
        return {
            "count": len(limited),
            "total": len(found),
            "searchDirectories": [
                str(directory) for directory in self._workspace.locator().search_directories
            ],
            "demos": [FileView.render(path) for path in limited],
        }

    def demos_inspect(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        demo_path = self._demo(payload)
        match = self._workspace.match(demo_path, refresh=bool(payload.get("refresh")))
        return MatchView.render(match)

    def match_rounds(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        demo_path = self._demo(payload)
        match = self._workspace.match(demo_path)
        wanted = SelectionCriteria.from_mapping({"rounds": payload.get("rounds")}).rounds
        include_kills = bool(payload.get("includeKills"))
        rounds = [
            RoundView.render(match, round_, include_kills)
            for round_ in match.rounds
            if not wanted or round_.number in wanted
        ]
        return {"demo": FileView.render(demo_path), "count": len(rounds), "rounds": rounds}

    def match_players(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        demo_path = self._demo(payload)
        match = self._workspace.match(demo_path)
        kills = {steam_id: 0 for steam_id in match.players}
        for round_ in match.rounds:
            for kill in round_.kills:
                if kill.attacker.steam_id64 in kills:
                    kills[kill.attacker.steam_id64] += 1

        players = []
        for player in sorted(match.players.values(), key=lambda item: -kills.get(item.steam_id64, 0)):
            document = PlayerView.render(player)
            document["killCount"] = kills.get(player.steam_id64, 0)
            players.append(document)
        return {"demo": FileView.render(demo_path), "count": len(players), "players": players}

    def highlights_find(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        demo_path = self._demo(payload)
        config = ConfigMerger.apply(self._workspace.config, payload.get("detection"))
        criteria = SelectionCriteria.from_mapping(payload.get("selection"))
        match = self._workspace.match(demo_path)
        found = self._workspace.highlights(demo_path, config.detection)
        selected = HighlightSelection(criteria).apply(found)
        return {
            "demo": FileView.render(demo_path),
            "map": match.map_name,
            "total": len(found),
            "count": len(selected),
            "selection": criteria.to_mapping(),
            "highlights": [HighlightView.render(match, item) for item in selected],
        }

    def grenades_find(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        demo_path = self._demo(payload)
        criteria = SelectionCriteria.from_mapping(payload.get("selection"))
        kinds = self._kinds(payload, criteria)
        match = self._workspace.match(demo_path)
        found = self._workspace.grenades(demo_path, kinds)
        selected = GrenadeSelection(criteria).apply(found)
        return {
            "demo": FileView.render(demo_path),
            "map": match.map_name,
            "kinds": [kind.value for kind in kinds],
            "total": len(found),
            "count": len(selected),
            "selection": criteria.to_mapping(),
            "places": sorted({item.landing_place for item in selected}),
            "grenades": [GrenadeView.render(match, item) for item in selected],
        }

    def plan_preview(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        demo_path = self._demo(payload)
        source = SourceKind.parse(payload.get("source"))
        criteria = SelectionCriteria.from_mapping(payload.get("selection"))
        config = ConfigMerger.apply(self._workspace.config, payload.get("overrides"))
        match = self._workspace.match(demo_path)
        output_root = self._workspace.paths.resolve(config.paths.output_directory)

        if source is SourceKind.GRENADES:
            selected = GrenadeSelection(criteria).apply(
                self._workspace.grenades(demo_path, self._kinds(payload, criteria))
            )
            self._require_selection(selected, source, criteria)
            plan: RecordingPlan = NadePlanBuilder(config.recording, config.nades).build(
                match, selected, output_root
            )
        else:
            selected = HighlightSelection(criteria).apply(
                self._workspace.highlights(demo_path, config.detection)
            )
            self._require_selection(selected, source, criteria)
            plan = RecordingPlanBuilder(config.recording).build(match, selected, output_root)

        return {"source": source.value, "plan": PlanView.render(plan)}

    def jobs_submit(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        demo_path = self._demo(payload)
        source = SourceKind.parse(payload.get("source"))
        criteria = SelectionCriteria.from_mapping(payload.get("selection"))
        overrides = payload.get("overrides") or {}
        if not isinstance(overrides, Mapping):
            raise BadRequestError("'overrides' must be a JSON object")
        config = ConfigMerger.apply(self._workspace.config, overrides)

        if bool(payload.get("validate", True)):
            self._validate(demo_path, source, criteria, config, payload)

        request = JobRequest(
            demo_path=demo_path,
            source=source,
            criteria=criteria,
            overrides=dict(overrides),
            label=str(payload.get("label") or ""),
        )
        record = self._jobs.submit(new_identifier(), request)
        return record.to_mapping()

    def jobs_get(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._job(payload).to_mapping()

    def jobs_list(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        state = self._state(payload.get("state"))
        limit = int(payload.get("limit") or 0)
        records = self._jobs.records(state, limit)
        return {
            "count": len(records),
            "busy": self._jobs.is_busy,
            "jobs": [record.to_mapping() for record in records],
        }

    def jobs_events(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        job_id = payload.get("jobId")
        if job_id is not None:
            self._job(payload)
        page = self._journal.read(
            since=int(payload.get("since") or 0),
            job_id=str(job_id) if job_id else None,
            limit=int(payload.get("limit") or DEFAULT_EVENT_LIMIT),
            wait_seconds=float(payload.get("waitSeconds") or 0.0),
        )
        return page.to_mapping()

    def jobs_cancel(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        record = self._job(payload)
        cancelled = self._jobs.cancel(record.identifier)
        return (cancelled or record).to_mapping()

    def jobs_result(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        record = self._job(payload)
        return {
            "jobId": record.identifier,
            "state": record.state.value,
            "result": record.result.to_mapping() if record.result else None,
            "error": record.error.to_mapping() if record.error else None,
        }

    def output_list(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        folder = self._output_folder(payload)
        videos = []
        if folder.is_dir():
            for candidate in sorted(folder.rglob("*")):
                if candidate.is_file() and candidate.suffix.lower() in VIDEO_SUFFIXES:
                    videos.append(FileView.render(candidate))
        return {"directory": str(folder), "count": len(videos), "videos": videos}

    def output_reveal(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        folder = self._output_folder(payload)
        opened = FolderOpener(enabled=True).open(folder)
        return {"directory": str(folder), "opened": opened}

    def shutdown(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        forced = bool(payload.get("force"))
        if self._jobs.is_busy and not forced:
            return {
                "stopping": False,
                "reason": "a recording is still running, pass force to stop anyway",
            }
        self._shutdown.set()
        return {"stopping": True, "reason": "forced" if forced else "idle"}

    def _output_folder(self, payload: Mapping[str, Any]) -> Path:
        root = self._workspace.paths.resolve(
            self._workspace.config.paths.output_directory
        )
        given = str(payload.get("demo") or "").strip()
        if not given:
            return root
        return root / self._demo(payload).stem

    def _validate(
        self,
        demo_path: Path,
        source: SourceKind,
        criteria: SelectionCriteria,
        config,
        payload: Mapping[str, Any],
    ) -> None:
        if source is SourceKind.GRENADES:
            matched = GrenadeSelection(criteria).apply(
                self._workspace.grenades(demo_path, self._kinds(payload, criteria))
            )
        else:
            matched = HighlightSelection(criteria).apply(
                self._workspace.highlights(demo_path, config.detection)
            )
        self._require_selection(matched, source, criteria)

    def _demo(self, payload: Mapping[str, Any]) -> Path:
        given = payload.get("demo")
        if given is None:
            raise BadRequestError("This command needs a 'demo' name or path")
        return self._workspace.resolve(str(given))

    def _job(self, payload: Mapping[str, Any]):
        identifier = str(payload.get("jobId") or "").strip()
        if not identifier:
            raise BadRequestError("This command needs a 'jobId'")
        record = self._jobs.get(identifier)
        if record is None:
            raise ApiError(
                ErrorCode.JOB_NOT_FOUND, f"No job with id {identifier}", {"jobId": identifier}
            )
        return record

    @staticmethod
    def _state(token: Any) -> JobState | None:
        if token is None:
            return None
        normalized = str(token).strip().lower()
        for candidate in JobState:
            if candidate.value == normalized:
                return candidate
        available = ", ".join(item.value for item in JobState)
        raise BadRequestError(f"Unknown job state {normalized}. Available: {available}")

    @staticmethod
    def _kinds(
        payload: Mapping[str, Any], criteria: SelectionCriteria
    ) -> tuple[GrenadeKind, ...]:
        explicit = SelectionCriteria.from_mapping({"grenadeKinds": payload.get("kinds")})
        return explicit.grenade_kinds or criteria.grenade_kinds or tuple(GrenadeKind)

    @staticmethod
    def _require_selection(selected: list, source: SourceKind, criteria: SelectionCriteria) -> None:
        if selected:
            return
        raise ApiError(
            ErrorCode.EMPTY_SELECTION,
            f"No {source.value} matched the selection",
            {"selection": criteria.to_mapping()},
        )
