from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from highlighter.recording.game_process import GameProcessWatcher

ABSENT_PROCESS = "highlighter_definitely_absent.exe"


def test_finds_a_running_process_and_its_pid():
    watcher = GameProcessWatcher(Path(sys.executable).name)

    assert watcher.is_running()
    assert os.getpid() in watcher.running_process_ids()


def test_absent_process_is_reported_as_stopped():
    watcher = GameProcessWatcher(ABSENT_PROCESS)

    assert watcher.is_running() is False
    assert watcher.running_process_ids() == []


def test_localised_tasklist_notice_is_not_mistaken_for_a_process():
    watcher = GameProcessWatcher(ABSENT_PROCESS)

    assert watcher.running_process_ids() == []


def test_wait_until_started_gives_up_after_the_timeout():
    watcher = GameProcessWatcher(ABSENT_PROCESS, poll_interval_seconds=0.05)

    started_at = time.monotonic()
    result = watcher.wait_until_started(0.3)

    assert result is False
    assert time.monotonic() - started_at >= 0.3


def test_wait_until_stopped_returns_immediately_for_an_absent_process():
    watcher = GameProcessWatcher(ABSENT_PROCESS, poll_interval_seconds=0.05)

    assert watcher.wait_until_stopped(5.0) is True


def test_wait_until_stopped_times_out_on_a_live_process():
    watcher = GameProcessWatcher(Path(sys.executable).name, poll_interval_seconds=0.05)

    assert watcher.wait_until_stopped(0.2) is False


def test_progress_callback_receives_elapsed_time():
    watcher = GameProcessWatcher(Path(sys.executable).name, poll_interval_seconds=0.05)
    samples: list[float] = []

    watcher.wait_until_stopped(0.3, samples.append)

    assert samples
    assert samples == sorted(samples)
    assert samples[0] >= 0.0
