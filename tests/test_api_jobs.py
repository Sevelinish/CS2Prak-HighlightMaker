from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from highlighter.api.errors import ApiError, ErrorCode
from highlighter.api.events import EventJournal, EventType
from highlighter.api.jobs import (
    JobQueue,
    JobRecord,
    JobRequest,
    JobResult,
    JobState,
    SourceKind,
)
from highlighter.api.selection import SelectionCriteria

STAGE_TOTAL = 8
WAIT_SECONDS = 5.0


def make_request(source: SourceKind = SourceKind.HIGHLIGHTS) -> JobRequest:
    return JobRequest(
        demo_path=Path("match.dem"),
        source=source,
        criteria=SelectionCriteria.from_mapping({"rounds": [3]}),
    )


def wait_for(queue: JobQueue, identifier: str, state: JobState) -> JobRecord:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        record = queue.get(identifier)
        if record is not None and record.state is state:
            return record
        time.sleep(0.02)
    raise AssertionError(f"job {identifier} never reached {state}")


@pytest.fixture
def journal():
    return EventJournal()


def build(journal, executor) -> JobQueue:
    queue = JobQueue(executor, journal, STAGE_TOTAL)
    queue.start()
    return queue


def test_a_submitted_job_runs_and_reports_its_result(journal):
    def executor(record, reporter):
        reporter.begin("Working")
        reporter.done("finished")
        return JobResult(output_directory="out", requested_clips=1)

    queue = build(journal, executor)
    try:
        submitted = queue.submit("job-1", make_request())
        record = wait_for(queue, submitted.identifier, JobState.SUCCEEDED)
    finally:
        queue.stop()

    assert record.result is not None
    assert record.result.output_directory == "out"
    assert record.error is None


def test_a_failing_job_keeps_the_error_code(journal):
    def executor(record, reporter):
        raise ApiError(ErrorCode.EMPTY_SELECTION, "nothing matched")

    queue = build(journal, executor)
    try:
        submitted = queue.submit("job-2", make_request())
        record = wait_for(queue, submitted.identifier, JobState.FAILED)
    finally:
        queue.stop()

    assert record.error is not None
    assert record.error.code is ErrorCode.EMPTY_SELECTION


def test_an_unexpected_failure_becomes_an_internal_error(journal):
    def executor(record, reporter):
        raise RuntimeError("boom")

    queue = build(journal, executor)
    try:
        submitted = queue.submit("job-3", make_request())
        record = wait_for(queue, submitted.identifier, JobState.FAILED)
    finally:
        queue.stop()

    assert record.error.code is ErrorCode.INTERNAL


def test_a_queued_job_is_cancelled_without_ever_running(journal):
    started = threading.Event()
    release = threading.Event()

    def executor(record, reporter):
        started.set()
        release.wait(WAIT_SECONDS)
        return JobResult()

    queue = build(journal, executor)
    try:
        first = queue.submit("job-4", make_request())
        second = queue.submit("job-5", make_request())
        started.wait(WAIT_SECONDS)

        cancelled = queue.cancel(second.identifier)
        assert cancelled.state is JobState.CANCELLED

        release.set()
        wait_for(queue, first.identifier, JobState.SUCCEEDED)
    finally:
        release.set()
        queue.stop()

    assert queue.get(second.identifier).state is JobState.CANCELLED


def test_cancelling_a_running_job_fires_its_hook(journal):
    hooked = threading.Event()
    entered = threading.Event()

    def executor(record, reporter):
        record.cancellation.register(hooked.set)
        entered.set()
        for _ in range(200):
            record.cancellation.raise_if_cancelled()
            time.sleep(0.02)
        return JobResult()

    queue = build(journal, executor)
    try:
        submitted = queue.submit("job-6", make_request())
        entered.wait(WAIT_SECONDS)
        queue.cancel(submitted.identifier)
        record = wait_for(queue, submitted.identifier, JobState.CANCELLED)
    finally:
        queue.stop()

    assert hooked.is_set()
    assert record.error is None


def test_jobs_run_one_at_a_time(journal):
    concurrent = []
    running = threading.Lock()
    counter = {"now": 0, "peak": 0}

    def executor(record, reporter):
        with running:
            counter["now"] += 1
            counter["peak"] = max(counter["peak"], counter["now"])
        time.sleep(0.05)
        with running:
            counter["now"] -= 1
        concurrent.append(record.identifier)
        return JobResult()

    queue = build(journal, executor)
    try:
        for index in range(4):
            queue.submit(f"job-7-{index}", make_request())
        for index in range(4):
            wait_for(queue, f"job-7-{index}", JobState.SUCCEEDED)
    finally:
        queue.stop()

    assert counter["peak"] == 1
    assert len(concurrent) == 4


def test_the_queue_position_tells_the_client_how_long_the_wait_is(journal):
    release = threading.Event()

    def executor(record, reporter):
        release.wait(WAIT_SECONDS)
        return JobResult()

    queue = build(journal, executor)
    try:
        queue.submit("job-8", make_request())
        second = queue.submit("job-9", make_request())
        third = queue.submit("job-10", make_request())

        assert second.queue_position >= 1
        assert third.queue_position > second.queue_position
    finally:
        release.set()
        queue.stop()


def test_events_describe_the_whole_life_of_a_job(journal):
    def executor(record, reporter):
        reporter.begin("Reading match.dem")
        reporter.detail("de_mirage")
        reporter.done("16 rounds")
        return JobResult()

    queue = build(journal, executor)
    try:
        submitted = queue.submit("job-11", make_request())
        wait_for(queue, submitted.identifier, JobState.SUCCEEDED)
    finally:
        queue.stop()

    types = [event.type for event in journal.read(job_id=submitted.identifier).events]

    assert types[0] == EventType.JOB_QUEUED
    assert EventType.JOB_STARTED in types
    assert EventType.STAGE_BEGIN in types
    assert EventType.STAGE_DETAIL in types
    assert types[-1] == EventType.JOB_SUCCEEDED


def test_events_are_read_from_a_sequence_number(journal):
    journal.publish("job-a", EventType.JOB_QUEUED)
    second = journal.publish("job-a", EventType.JOB_STARTED)

    page = journal.read(since=second.sequence - 1)

    assert [event.sequence for event in page.events] == [second.sequence]
    assert page.next_sequence == second.sequence


def test_events_can_be_read_for_one_job_only(journal):
    journal.publish("job-a", EventType.JOB_QUEUED)
    journal.publish("job-b", EventType.JOB_QUEUED)

    page = journal.read(job_id="job-b")

    assert [event.job_id for event in page.events] == ["job-b"]


def test_a_long_poll_returns_as_soon_as_an_event_arrives(journal):
    def publish_soon():
        time.sleep(0.1)
        journal.publish("job-c", EventType.JOB_STARTED)

    threading.Thread(target=publish_soon, daemon=True).start()
    started_at = time.monotonic()
    page = journal.read(since=0, wait_seconds=WAIT_SECONDS)

    assert page.events
    assert time.monotonic() - started_at < WAIT_SECONDS


def test_a_long_poll_gives_up_when_nothing_happens(journal):
    page = journal.read(since=journal.last_sequence, wait_seconds=0.2)

    assert page.events == ()


def test_the_journal_forgets_the_oldest_events():
    journal = EventJournal(capacity=5)
    for index in range(12):
        journal.publish("job-d", EventType.STAGE_DETAIL, {"index": index})

    page = journal.read(since=0)

    assert len(page.events) == 5
    assert page.last_sequence == 12


def test_an_unknown_source_is_rejected():
    with pytest.raises(ApiError) as raised:
        SourceKind.parse("replays")

    assert raised.value.code is ErrorCode.BAD_REQUEST


def test_the_default_source_is_highlights():
    assert SourceKind.parse(None) is SourceKind.HIGHLIGHTS
    assert SourceKind.parse("grenades") is SourceKind.GRENADES


def test_a_job_serialises_everything_a_launcher_needs(journal):
    queue = JobQueue(lambda record, reporter: JobResult(), journal, STAGE_TOTAL)
    document = queue.submit("job-12", make_request(SourceKind.GRENADES)).to_mapping()

    assert document["jobId"] == "job-12"
    assert document["state"] == "queued"
    assert document["request"]["source"] == "grenades"
    assert document["request"]["selection"]["rounds"] == [3]
    assert document["progress"]["total"] == STAGE_TOTAL
