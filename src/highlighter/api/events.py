from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Mapping

MAXIMUM_JOURNAL_ENTRIES = 4000
DEFAULT_PAGE_SIZE = 200
MAXIMUM_WAIT_SECONDS = 60.0


class EventType:
    JOB_QUEUED = "job.queued"
    JOB_STARTED = "job.started"
    JOB_SUCCEEDED = "job.succeeded"
    JOB_FAILED = "job.failed"
    JOB_CANCELLED = "job.cancelled"
    STAGE_BEGIN = "stage.begin"
    STAGE_DETAIL = "stage.detail"
    STAGE_END = "stage.end"
    STAGE_FAILED = "stage.failed"
    PLAN_READY = "plan.ready"
    CLIP_WRITTEN = "clip.written"


@dataclass(frozen=True, slots=True)
class ApiEvent:
    sequence: int
    job_id: str
    type: str
    timestamp: float
    data: Mapping[str, Any] = field(default_factory=dict)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "kind": "event",
            "sequence": self.sequence,
            "jobId": self.job_id,
            "type": self.type,
            "timestamp": round(self.timestamp, 3),
            "data": dict(self.data),
        }


@dataclass(frozen=True, slots=True)
class EventPage:
    events: tuple[ApiEvent, ...]
    next_sequence: int
    last_sequence: int

    def to_mapping(self) -> dict[str, Any]:
        return {
            "events": [event.to_mapping() for event in self.events],
            "nextSequence": self.next_sequence,
            "lastSequence": self.last_sequence,
        }


class EventJournal:
    def __init__(self, capacity: int = MAXIMUM_JOURNAL_ENTRIES) -> None:
        self._entries: deque[ApiEvent] = deque(maxlen=capacity)
        self._sequence = 0
        self._condition = threading.Condition()

    def publish(
        self,
        job_id: str,
        event_type: str,
        data: Mapping[str, Any] | None = None,
    ) -> ApiEvent:
        with self._condition:
            self._sequence += 1
            event = ApiEvent(
                sequence=self._sequence,
                job_id=job_id,
                type=event_type,
                timestamp=time.time(),
                data=dict(data or {}),
            )
            self._entries.append(event)
            self._condition.notify_all()
            return event

    @property
    def last_sequence(self) -> int:
        with self._condition:
            return self._sequence

    def read(
        self,
        since: int = 0,
        job_id: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        wait_seconds: float = 0.0,
    ) -> EventPage:
        deadline = time.monotonic() + min(max(0.0, wait_seconds), MAXIMUM_WAIT_SECONDS)
        while True:
            with self._condition:
                collected = self._collect(since, job_id, limit)
                if collected or time.monotonic() >= deadline:
                    return EventPage(
                        events=tuple(collected),
                        next_sequence=(
                            collected[-1].sequence if collected else max(since, 0)
                        ),
                        last_sequence=self._sequence,
                    )
                self._condition.wait(timeout=max(0.0, deadline - time.monotonic()))

    def _collect(self, since: int, job_id: str | None, limit: int) -> list[ApiEvent]:
        collected: list[ApiEvent] = []
        for event in self._entries:
            if event.sequence <= since:
                continue
            if job_id is not None and event.job_id != job_id:
                continue
            collected.append(event)
            if limit and len(collected) >= limit:
                break
        return collected


class JobProgressReporter:
    def __init__(self, journal: EventJournal, job_id: str, total_stages: int) -> None:
        self._journal = journal
        self._job_id = job_id
        self._total_stages = total_stages
        self._index = 0
        self._title = ""
        self._open = False

    @property
    def stage_index(self) -> int:
        return self._index

    @property
    def stage_title(self) -> str:
        return self._title

    def begin(self, title: str) -> None:
        self._index += 1
        self._title = title
        self._open = True
        self._journal.publish(
            self._job_id,
            EventType.STAGE_BEGIN,
            {"stage": self._index, "total": self._total_stages, "title": title},
        )

    def detail(self, message: str) -> None:
        self._journal.publish(
            self._job_id,
            EventType.STAGE_DETAIL,
            {"stage": self._index, "title": self._title, "message": message},
        )

    def done(self, note: str = "") -> None:
        if not self._open:
            return
        self._open = False
        self._journal.publish(
            self._job_id,
            EventType.STAGE_END,
            {
                "stage": self._index,
                "total": self._total_stages,
                "title": self._title,
                "note": note,
            },
        )

    def fail(self, note: str = "") -> None:
        if not self._open:
            return
        self._open = False
        self._journal.publish(
            self._job_id,
            EventType.STAGE_FAILED,
            {
                "stage": self._index,
                "total": self._total_stages,
                "title": self._title,
                "note": note,
            },
        )

    def publish(self, event_type: str, data: Mapping[str, Any] | None = None) -> None:
        self._journal.publish(self._job_id, event_type, data)
