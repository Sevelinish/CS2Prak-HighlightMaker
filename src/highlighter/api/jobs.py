from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping

from .errors import ApiError, ErrorCode, ErrorTranslator
from .events import EventJournal, EventType, JobProgressReporter
from .selection import SelectionCriteria

DEFAULT_HISTORY_LIMIT = 50
WORKER_POLL_SECONDS = 0.2


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_final(self) -> bool:
        return self in {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED}


class SourceKind(str, Enum):
    HIGHLIGHTS = "highlights"
    GRENADES = "grenades"

    @classmethod
    def parse(cls, token: Any) -> "SourceKind":
        normalized = str(token or cls.HIGHLIGHTS.value).strip().lower()
        for candidate in cls:
            if normalized == candidate.value:
                return candidate
        available = ", ".join(item.value for item in cls)
        raise ApiError(
            ErrorCode.BAD_REQUEST,
            f"Unknown source {normalized}. Available: {available}",
        )


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()
        self._hooks: list[Callable[[], None]] = []
        self._lock = threading.Lock()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def register(self, hook: Callable[[], None]) -> None:
        with self._lock:
            self._hooks.append(hook)
        if self.is_cancelled:
            hook()

    def clear_hooks(self) -> None:
        with self._lock:
            self._hooks.clear()

    def cancel(self) -> None:
        self._event.set()
        with self._lock:
            hooks = list(self._hooks)
        for hook in hooks:
            hook()

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise JobCancelledError()


class JobCancelledError(ApiError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.CANCELLED, "The job was cancelled")


@dataclass(frozen=True, slots=True)
class JobRequest:
    demo_path: Path
    source: SourceKind
    criteria: SelectionCriteria
    overrides: Mapping[str, Any] = field(default_factory=dict)
    label: str = ""

    def to_mapping(self) -> dict[str, Any]:
        return {
            "demo": str(self.demo_path),
            "demoName": self.demo_path.stem,
            "source": self.source.value,
            "selection": self.criteria.to_mapping(),
            "overrides": dict(self.overrides),
            "label": self.label,
        }


@dataclass(slots=True)
class JobArtifact:
    name: str
    path: str
    kind: str
    duration_seconds: float = 0.0
    segment_count: int = 1
    has_audio: bool = True

    def to_mapping(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "kind": self.kind,
            "durationSeconds": round(self.duration_seconds, 2),
            "segmentCount": self.segment_count,
            "hasAudio": self.has_audio,
        }


@dataclass(slots=True)
class JobResult:
    output_directory: str = ""
    requested_clips: int = 0
    artifacts: list[JobArtifact] = field(default_factory=list)
    reel: JobArtifact | None = None
    reused_game: bool = False
    warm_session: Mapping[str, Any] | None = None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "outputDirectory": self.output_directory,
            "requestedClips": self.requested_clips,
            "producedClips": len(self.artifacts),
            "artifacts": [item.to_mapping() for item in self.artifacts],
            "reel": self.reel.to_mapping() if self.reel else None,
            "reusedGame": self.reused_game,
            "warmSession": dict(self.warm_session) if self.warm_session else None,
        }


@dataclass(slots=True)
class JobRecord:
    identifier: str
    request: JobRequest
    state: JobState = JobState.QUEUED
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    finished_at: float = 0.0
    stage: int = 0
    stage_total: int = 0
    stage_title: str = ""
    queue_position: int = 0
    plan: Mapping[str, Any] | None = None
    result: JobResult | None = None
    error: ApiError | None = None
    cancellation: CancellationToken = field(default_factory=CancellationToken)

    @property
    def elapsed_seconds(self) -> float:
        if not self.started_at:
            return 0.0
        end = self.finished_at or time.time()
        return max(0.0, end - self.started_at)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "jobId": self.identifier,
            "state": self.state.value,
            "request": self.request.to_mapping(),
            "createdAt": round(self.created_at, 3),
            "startedAt": round(self.started_at, 3),
            "finishedAt": round(self.finished_at, 3),
            "elapsedSeconds": round(self.elapsed_seconds, 2),
            "queuePosition": self.queue_position,
            "progress": {
                "stage": self.stage,
                "total": self.stage_total,
                "title": self.stage_title,
            },
            "plan": dict(self.plan) if self.plan else None,
            "result": self.result.to_mapping() if self.result else None,
            "error": self.error.to_mapping() if self.error else None,
        }


JobExecutor = Callable[[JobRecord, JobProgressReporter], JobResult]


class JobQueue:
    def __init__(
        self,
        executor: JobExecutor,
        journal: EventJournal,
        stage_total: int,
        history_limit: int = DEFAULT_HISTORY_LIMIT,
    ) -> None:
        self._executor = executor
        self._journal = journal
        self._stage_total = stage_total
        self._history_limit = history_limit
        self._records: dict[str, JobRecord] = {}
        self._order: list[str] = []
        self._pending: list[str] = []
        self._condition = threading.Condition()
        self._worker: threading.Thread | None = None
        self._stopping = False

    def start(self) -> None:
        with self._condition:
            if self._worker is not None:
                return
            self._stopping = False
            self._worker = threading.Thread(target=self._serve, name="highlighter-jobs", daemon=True)
            self._worker.start()

    def stop(self, timeout_seconds: float = 5.0) -> None:
        with self._condition:
            self._stopping = True
            worker = self._worker
            self._condition.notify_all()
        if worker is not None:
            worker.join(timeout=timeout_seconds)
        with self._condition:
            self._worker = None

    @property
    def is_busy(self) -> bool:
        with self._condition:
            return any(
                self._records[identifier].state is JobState.RUNNING
                for identifier in self._order
            )

    def submit(self, identifier: str, request: JobRequest) -> JobRecord:
        record = JobRecord(identifier=identifier, request=request, stage_total=self._stage_total)
        with self._condition:
            self._records[identifier] = record
            self._order.insert(0, identifier)
            self._pending.append(identifier)
            record.queue_position = len(self._pending)
            self._trim()
            self._condition.notify_all()
        self._journal.publish(
            identifier,
            EventType.JOB_QUEUED,
            {"queuePosition": record.queue_position, "request": request.to_mapping()},
        )
        return record

    def get(self, identifier: str) -> JobRecord | None:
        with self._condition:
            return self._records.get(identifier)

    def records(self, state: JobState | None = None, limit: int = 0) -> list[JobRecord]:
        with self._condition:
            collected = [
                self._records[identifier]
                for identifier in self._order
                if state is None or self._records[identifier].state is state
            ]
        return collected[:limit] if limit else collected

    def cancel(self, identifier: str) -> JobRecord | None:
        with self._condition:
            record = self._records.get(identifier)
            if record is None or record.state.is_final:
                return record
            was_queued = record.state is JobState.QUEUED
            if was_queued and identifier in self._pending:
                self._pending.remove(identifier)
            record.cancellation.cancel()
            if was_queued:
                self._finish(record, JobState.CANCELLED)
            self._condition.notify_all()

        if record is not None and record.state is JobState.CANCELLED:
            self._journal.publish(identifier, EventType.JOB_CANCELLED, {"whileQueued": True})
        return record

    def _serve(self) -> None:
        while True:
            with self._condition:
                while not self._pending and not self._stopping:
                    self._condition.wait(timeout=WORKER_POLL_SECONDS)
                if self._stopping and not self._pending:
                    return
                identifier = self._pending.pop(0)
                record = self._records[identifier]
                self._renumber()
            self._run(record)

    def _run(self, record: JobRecord) -> None:
        if record.cancellation.is_cancelled:
            with self._condition:
                self._finish(record, JobState.CANCELLED)
            self._journal.publish(record.identifier, EventType.JOB_CANCELLED, {})
            return

        with self._condition:
            record.state = JobState.RUNNING
            record.started_at = time.time()
            record.queue_position = 0
        self._journal.publish(
            record.identifier, EventType.JOB_STARTED, {"request": record.request.to_mapping()}
        )

        reporter = JobProgressReporter(self._journal, record.identifier, self._stage_total)
        try:
            result = self._executor(record, reporter)
        except BaseException as error:
            self._fail(record, reporter, error)
            return
        finally:
            record.cancellation.clear_hooks()

        with self._condition:
            record.result = result
            self._finish(record, JobState.SUCCEEDED)
        self._journal.publish(
            record.identifier, EventType.JOB_SUCCEEDED, {"result": result.to_mapping()}
        )

    def _fail(
        self, record: JobRecord, reporter: JobProgressReporter, error: BaseException
    ) -> None:
        translated = ErrorTranslator.translate(error)
        cancelled = record.cancellation.is_cancelled or isinstance(error, JobCancelledError)
        reporter.fail(translated.message)

        with self._condition:
            record.error = None if cancelled else translated
            self._finish(record, JobState.CANCELLED if cancelled else JobState.FAILED)

        if cancelled:
            self._journal.publish(record.identifier, EventType.JOB_CANCELLED, {})
            return
        self._journal.publish(
            record.identifier, EventType.JOB_FAILED, {"error": translated.to_mapping()}
        )

    def _finish(self, record: JobRecord, state: JobState) -> None:
        record.state = state
        record.finished_at = time.time()
        record.queue_position = 0

    def _renumber(self) -> None:
        for position, identifier in enumerate(self._pending, start=1):
            self._records[identifier].queue_position = position

    def _trim(self) -> None:
        while len(self._order) > self._history_limit:
            identifier = self._order[-1]
            if self._records[identifier].state.is_final:
                self._order.pop()
                self._records.pop(identifier, None)
                continue
            return


class JobStageTracker:
    def __init__(self, record: JobRecord, reporter: JobProgressReporter) -> None:
        self._record = record
        self._reporter = reporter

    def begin(self, title: str) -> None:
        self._record.cancellation.raise_if_cancelled()
        self._reporter.begin(title)
        self._record.stage = self._reporter.stage_index
        self._record.stage_title = title

    def detail(self, message: str) -> None:
        self._reporter.detail(message)

    def done(self, note: str = "") -> None:
        self._reporter.done(note)

    def fail(self, note: str = "") -> None:
        self._reporter.fail(note)

    def publish(self, event_type: str, data: Mapping[str, Any] | None = None) -> None:
        self._reporter.publish(event_type, data)
