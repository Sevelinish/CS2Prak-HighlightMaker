from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from highlighter.config.schema import GameConfig, RecordingConfig
from highlighter.media.encoders import EncoderProfile
from highlighter.plan.models import ClipPlayer, ClipSegment, ClipSpec, RecordingPlan
from highlighter.recording.mirv_script import (
    BOOTSTRAP_TICK,
    FINISH_SCRIPT_NAME,
    HANDOVER_SCRIPT_NAME,
    LISTEN_SCRIPT_NAME,
    MirvScriptBuilder,
)
from highlighter.recording.script_writer import ScriptWriter
from highlighter.recording.take_watcher import TakeWatcher
from highlighter.recording.warm_session import WarmSession, WarmSessionStore

ENCODER = EncoderProfile("libx264", ("-c:v", "libx264"), "mp4", False)
TICK_RATE = 64


def make_plan(demo: str = "match.dem", segments: int = 1, end_tick: int = 40_000) -> RecordingPlan:
    plan = RecordingPlan(
        demo_path=Path(demo),
        demo_name=Path(demo).stem,
        map_name="de_mirage",
        tick_rate=TICK_RATE,
        fps=60,
        width=1920,
        height=1080,
        output_directory=Path("out"),
        demo_end_tick=end_tick,
    )
    plan.clips.append(
        ClipSpec(
            index=1,
            name="c1",
            round_number=3,
            player=ClipPlayer("kul", 76561198000000000, 39734272, 5),
            tags=(),
            score=1.0,
            segments=tuple(
                ClipSegment(
                    index=index + 1,
                    start_tick=10_000 + index * 2_000,
                    end_tick=10_600 + index * 2_000,
                    kill_ticks=(10_200 + index * 2_000,),
                    duration_seconds=9.4,
                )
                for index in range(segments)
            ),
            action_start_tick=10_200,
            action_end_tick=10_400,
        )
    )
    return plan


def build(recording: RecordingConfig, plan: RecordingPlan, handover: bool = False):
    return MirvScriptBuilder(recording, ENCODER, GameConfig(), Path("takes")).build(
        plan, handover=handover
    )


def script(bundle, name: str) -> str:
    return next(item.content for item in bundle.files if item.name == name)


def test_a_normal_run_still_quits_the_game():
    bundle = build(RecordingConfig(), make_plan())

    assert "quit" in script(bundle, "highlighter_c01_s01_end")


def test_keeping_the_game_open_never_quits():
    bundle = build(RecordingConfig(keep_game_open=True), make_plan())

    assert "quit" not in script(bundle, "highlighter_c01_s01_end")


def test_the_last_segment_hands_over_to_the_finish_script():
    bundle = build(RecordingConfig(keep_game_open=True), make_plan())
    lines = script(bundle, "highlighter_c01_s01_end").splitlines()

    assert lines == ["mirv_streams record end", f"exec {FINISH_SCRIPT_NAME}"]


def test_the_default_finish_parks_the_demo_and_listens():
    bundle = build(RecordingConfig(keep_game_open=True), make_plan())
    lines = script(bundle, FINISH_SCRIPT_NAME).splitlines()

    assert lines == [
        "mirv_cmd clear",
        f"exec {LISTEN_SCRIPT_NAME}",
        f"demo_gototick {BOOTSTRAP_TICK}",
    ]


def test_the_schedule_is_cleared_before_the_rewind():
    lines = MirvScriptBuilder.park_script().splitlines()

    assert lines.index("mirv_cmd clear") < lines.index(f"demo_gototick {BOOTSTRAP_TICK}")


def test_the_console_finish_closes_the_demo():
    lines = MirvScriptBuilder.disconnect_script().splitlines()

    assert lines == ["mirv_cmd clear", "disconnect"]


def test_only_the_last_segment_finishes():
    bundle = build(RecordingConfig(keep_game_open=True), make_plan(segments=2))
    first = script(bundle, "highlighter_c01_s01_end")

    assert FINISH_SCRIPT_NAME not in first
    assert FINISH_SCRIPT_NAME in script(bundle, "highlighter_c01_s02_end")


def test_the_listener_is_armed_across_the_demo():
    bundle = build(RecordingConfig(keep_game_open=True), make_plan(end_tick=40_000))
    lines = script(bundle, LISTEN_SCRIPT_NAME).splitlines()
    ticks = [int(line.split()[2]) for line in lines]

    assert all(line.endswith(f"exec {HANDOVER_SCRIPT_NAME}") for line in lines)
    assert ticks[0] > BOOTSTRAP_TICK
    assert ticks[-1] <= 40_000


def test_the_listener_starts_after_the_rewind_has_settled():
    bundle = build(RecordingConfig(keep_game_open=True), make_plan())
    first = int(script(bundle, LISTEN_SCRIPT_NAME).splitlines()[0].split()[2])

    assert first - BOOTSTRAP_TICK >= TICK_RATE


def test_the_listener_cadence_follows_the_setting():
    settings = RecordingConfig(keep_game_open=True, handover_interval_seconds=2.0)
    lines = script(build(settings, make_plan()), LISTEN_SCRIPT_NAME).splitlines()
    ticks = [int(line.split()[2]) for line in lines]

    assert ticks[1] - ticks[0] == 2 * TICK_RATE


def test_a_long_demo_does_not_produce_an_endless_listener():
    settings = RecordingConfig(keep_game_open=True, handover_interval_seconds=0.1)
    lines = script(build(settings, make_plan(end_tick=5_000_000)), LISTEN_SCRIPT_NAME)

    assert len(lines.splitlines()) <= 4000


def test_a_demo_without_an_end_tick_still_listens():
    bundle = build(RecordingConfig(keep_game_open=True), make_plan(end_tick=0))

    assert script(bundle, LISTEN_SCRIPT_NAME).strip()


def test_no_listener_is_written_when_the_game_should_close():
    names = {item.name for item in build(RecordingConfig(), make_plan()).files}

    assert LISTEN_SCRIPT_NAME not in names


def test_a_handover_script_execs_the_session_then_seeks():
    bundle = build(RecordingConfig(keep_game_open=True), make_plan(), handover=True)
    lines = script(bundle, HANDOVER_SCRIPT_NAME).splitlines()

    assert lines[0] == "exec highlighter_session"
    assert lines[1].startswith("demo_gototick ")
    assert bundle.hands_over is True


def test_the_handover_seek_leaves_room_before_the_first_segment():
    settings = RecordingConfig(keep_game_open=True, seek_lead_ticks=128)
    bundle = build(settings, make_plan(), handover=True)
    destination = int(script(bundle, HANDOVER_SCRIPT_NAME).splitlines()[1].split()[1])

    assert destination == 10_000 - 128


def test_no_handover_script_is_written_for_a_cold_launch():
    bundle = build(RecordingConfig(keep_game_open=True), make_plan(), handover=False)

    assert bundle.hands_over is False
    assert HANDOVER_SCRIPT_NAME not in {item.name for item in bundle.files}


def test_the_handover_script_is_written_last(tmp_path):
    config_directory = tmp_path / "cfg"
    config_directory.mkdir()
    bundle = build(RecordingConfig(keep_game_open=True), make_plan(), handover=True)

    written = ScriptWriter(config_directory).write(bundle)

    assert written[-1].name == f"{HANDOVER_SCRIPT_NAME}.cfg"


def test_the_handover_script_can_be_dropped_on_its_own(tmp_path):
    config_directory = tmp_path / "cfg"
    config_directory.mkdir()
    writer = ScriptWriter(config_directory)
    writer.write(build(RecordingConfig(keep_game_open=True), make_plan(), handover=True))

    assert writer.drop(HANDOVER_SCRIPT_NAME) is True
    assert not (config_directory / f"{HANDOVER_SCRIPT_NAME}.cfg").exists()
    assert (config_directory / f"{LISTEN_SCRIPT_NAME}.cfg").exists()


def test_dropping_a_script_that_is_gone_says_so(tmp_path):
    config_directory = tmp_path / "cfg"
    config_directory.mkdir()

    assert ScriptWriter(config_directory).drop(HANDOVER_SCRIPT_NAME) is False


def make_session(tmp_path: Path, **overrides) -> WarmSession:
    defaults = dict(
        pid=4242,
        executable="cs2.exe",
        demo_path=str(Path("match.dem")),
        demo_name="match",
        config_directory=str(tmp_path),
        handover_script=HANDOVER_SCRIPT_NAME,
        width=1920,
        height=1080,
        fullscreen=False,
        started_at=time.time(),
        expires_at=time.time() + 600,
    )
    defaults.update(overrides)
    return WarmSession(**defaults)


def test_a_saved_session_reads_back_the_same(tmp_path):
    store = WarmSessionStore(tmp_path)
    store._write(make_session(tmp_path))

    loaded = store.load()

    assert loaded is not None
    assert loaded.pid == 4242
    assert loaded.demo_name == "match"


def test_a_session_from_another_version_is_ignored(tmp_path):
    marker = tmp_path / "warm_session.json"
    marker.write_text(json.dumps({"version": 99, "pid": 1}), encoding="utf-8")

    assert WarmSessionStore(tmp_path).load() is None


def test_a_broken_marker_is_ignored(tmp_path):
    (tmp_path / "warm_session.json").write_text("{not json", encoding="utf-8")

    assert WarmSessionStore(tmp_path).load() is None


def test_a_missing_marker_is_no_session(tmp_path):
    assert WarmSessionStore(tmp_path).load() is None


def test_clearing_removes_the_marker(tmp_path):
    store = WarmSessionStore(tmp_path)
    store._write(make_session(tmp_path))

    store.clear()

    assert store.load() is None


def test_an_expired_session_is_not_reused(tmp_path):
    session = make_session(tmp_path, expires_at=time.time() - 1)

    assert session.is_expired is True
    assert session.seconds_left == 0.0


def test_a_session_for_another_demo_does_not_fit(tmp_path):
    session = make_session(tmp_path)

    assert session.fits(make_plan("other.dem"), RecordingConfig()) is False


def test_a_session_at_another_resolution_does_not_fit(tmp_path):
    session = make_session(tmp_path)

    assert session.fits(make_plan(), RecordingConfig(width=2560, height=1440)) is False


def test_a_session_in_the_other_window_mode_does_not_fit(tmp_path):
    session = make_session(tmp_path)

    assert session.fits(make_plan(), RecordingConfig(fullscreen=True)) is False


def test_a_matching_session_fits(tmp_path):
    assert make_session(tmp_path).fits(make_plan(), RecordingConfig()) is True


def test_the_warm_window_follows_the_demo_length(tmp_path):
    store = WarmSessionStore(tmp_path)

    short = store._window_seconds(make_plan(end_tick=TICK_RATE * 120))
    long = store._window_seconds(make_plan(end_tick=TICK_RATE * 2400))

    assert long > short
    assert short >= 60.0


def test_a_demo_of_unknown_length_still_gets_a_window(tmp_path):
    assert WarmSessionStore(tmp_path)._window_seconds(make_plan(end_tick=0)) >= 60.0


def write_take(root: Path, clip: str, segment: str, size: int) -> None:
    folder = root / clip / segment / "stream"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "video.mp4").write_bytes(b"0" * size)


def test_an_empty_take_directory_has_not_started(tmp_path):
    watcher = TakeWatcher(make_plan(), tmp_path, settle_seconds=0.0, stall_seconds=1.0)

    assert watcher.snapshot().has_started is False
    assert watcher.segment_count == 1


def test_a_written_take_counts_as_started(tmp_path):
    watcher = TakeWatcher(make_plan(), tmp_path, settle_seconds=0.0, stall_seconds=1.0)
    write_take(tmp_path, "c1", "s01", 2048)

    snapshot = watcher.snapshot()

    assert snapshot.has_started is True
    assert snapshot.is_complete is True
    assert snapshot.bytes_written == 2048


def test_a_half_written_plan_is_not_complete(tmp_path):
    watcher = TakeWatcher(make_plan(segments=2), tmp_path, settle_seconds=0.0, stall_seconds=1.0)
    write_take(tmp_path, "c1", "s01", 1024)

    snapshot = watcher.snapshot()

    assert snapshot.completed == 1
    assert snapshot.total == 2
    assert snapshot.is_complete is False


def test_the_watcher_returns_once_every_take_settles(tmp_path):
    watcher = TakeWatcher(
        make_plan(), tmp_path, settle_seconds=0.0, stall_seconds=5.0, poll_interval_seconds=0.01
    )
    write_take(tmp_path, "c1", "s01", 512)

    progress = watcher.wait(timeout_seconds=5.0)

    assert progress.is_complete is True


def test_the_watcher_gives_up_when_nothing_is_written(tmp_path):
    watcher = TakeWatcher(
        make_plan(), tmp_path, settle_seconds=0.0, stall_seconds=0.05, poll_interval_seconds=0.01
    )

    progress = watcher.wait(timeout_seconds=5.0)

    assert progress.completed == 0


def test_the_watcher_stops_when_the_game_is_gone(tmp_path):
    watcher = TakeWatcher(
        make_plan(), tmp_path, settle_seconds=0.0, stall_seconds=5.0, poll_interval_seconds=0.01
    )

    progress = watcher.wait(timeout_seconds=5.0, is_alive=lambda: False)

    assert progress.is_complete is False


def test_waiting_for_a_start_that_never_comes_reports_false(tmp_path):
    watcher = TakeWatcher(
        make_plan(), tmp_path, settle_seconds=0.0, stall_seconds=5.0, poll_interval_seconds=0.01
    )

    assert watcher.wait_for_start(timeout_seconds=0.05) is False


def test_waiting_for_a_start_that_arrives_reports_true(tmp_path):
    watcher = TakeWatcher(
        make_plan(), tmp_path, settle_seconds=0.0, stall_seconds=5.0, poll_interval_seconds=0.01
    )
    write_take(tmp_path, "c1", "s01", 64)

    assert watcher.wait_for_start(timeout_seconds=1.0) is True


def test_the_exit0_flag_keeps_the_game_open():
    from highlighter.cli import CommandLine

    assert CommandLine.parse(["m.dem", "-exit0"]).keep_game_open is True
    assert CommandLine.parse(["m.dem", "--exit0"]).keep_game_open is True
    assert CommandLine.parse(["m.dem", "--keep-game-open"]).keep_game_open is True


def test_without_the_flag_the_game_still_closes():
    from highlighter.cli import CommandLine

    assert CommandLine.parse(["m.dem"]).keep_game_open is False


def test_the_flag_survives_a_player_name_starting_with_a_dash():
    from highlighter.cli import CommandLine

    parsed = CommandLine.parse(["m.dem", "-p", "-n1clxe", "-exit0"])

    assert parsed.player == "-n1clxe"
    assert parsed.keep_game_open is True


def test_the_setting_reaches_the_config():
    assert RecordingConfig.from_mapping({"keepGameOpen": True}).keep_game_open is True
    assert RecordingConfig().to_mapping()["keepGameOpen"] is False


def test_a_job_can_ask_for_the_game_to_stay_open():
    from highlighter.api.service import PluginService

    merged = PluginService._with_keep_game_open({}, {"keepGameOpen": True})

    assert merged["recording"]["keepGameOpen"] is True


def test_asking_for_the_game_to_stay_open_keeps_other_overrides():
    from highlighter.api.service import PluginService

    merged = PluginService._with_keep_game_open(
        {"recording": {"fps": 120}, "encoding": {"quality": 16}}, {"keepGameOpen": True}
    )

    assert merged["recording"] == {"fps": 120, "keepGameOpen": True}
    assert merged["encoding"] == {"quality": 16}


def test_an_explicit_override_is_left_alone_when_the_field_is_absent():
    from highlighter.api.service import PluginService

    merged = PluginService._with_keep_game_open({"recording": {"keepGameOpen": True}}, {})

    assert merged["recording"]["keepGameOpen"] is True


def test_the_job_result_reports_whether_the_game_was_reused():
    from highlighter.api.jobs import JobResult

    document = JobResult(reused_game=True).to_mapping()

    assert document["reusedGame"] is True
    assert document["warmSession"] is None


def test_the_stall_timer_does_not_run_while_the_game_is_still_loading(tmp_path):
    watcher = TakeWatcher(
        make_plan(), tmp_path, settle_seconds=0.0, stall_seconds=0.05, poll_interval_seconds=0.01
    )
    polls = {"count": 0}

    def still_loading() -> bool:
        polls["count"] += 1
        if polls["count"] > 20:
            write_take(tmp_path, "c1", "s01", 256)
        return True

    progress = watcher.wait(timeout_seconds=5.0, is_alive=still_loading)

    assert progress.is_complete is True


def test_a_recording_that_dies_mid_way_still_stalls_out(tmp_path):
    watcher = TakeWatcher(
        make_plan(segments=2),
        tmp_path,
        settle_seconds=0.0,
        stall_seconds=0.05,
        poll_interval_seconds=0.01,
    )
    write_take(tmp_path, "c1", "s01", 128)

    progress = watcher.wait(timeout_seconds=5.0)

    assert progress.completed == 1
    assert progress.is_complete is False


def test_the_console_port_is_passed_to_the_game():
    from highlighter.recording.netcon import NetconEndpoint

    arguments = NetconEndpoint(port=4242, password="hunter2").launch_arguments()

    assert arguments == ["-netconport", "4242", "-netconpassword", "hunter2"]


def test_no_console_port_means_no_launch_arguments():
    from highlighter.recording.netcon import NetconEndpoint

    assert NetconEndpoint(port=0).launch_arguments() == []


def test_a_created_endpoint_picks_a_free_port_and_a_password():
    from highlighter.recording.netcon import NetconEndpoint

    endpoint = NetconEndpoint.create()

    assert endpoint.port > 0
    assert len(endpoint.password) >= 8
    assert endpoint.host == "127.0.0.1"


def test_an_explicit_console_port_is_kept():
    from highlighter.recording.netcon import NetconEndpoint

    assert NetconEndpoint.create(port=31337).port == 31337


def test_a_dead_console_port_is_not_reachable():
    from highlighter.recording.netcon import NetconClient, NetconEndpoint, free_port

    client = NetconClient(NetconEndpoint(port=free_port()), timeout_seconds=0.2)

    assert client.is_reachable() is False
    assert client.send(["echo hi"]) is False


def test_commands_reach_a_listening_console():
    import socket
    import threading

    from highlighter.recording.netcon import NetconClient, NetconEndpoint

    received: list[str] = []
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def accept() -> None:
        connection, _ = server.accept()
        with connection:
            connection.settimeout(2.0)
            payload = b""
            while b"playdemo" not in payload:
                chunk = connection.recv(4096)
                if not chunk:
                    break
                payload += chunk
        received.extend(payload.decode("utf-8").splitlines())

    worker = threading.Thread(target=accept, daemon=True)
    worker.start()

    endpoint = NetconEndpoint(port=port, password="hunter2")
    sent = NetconClient(endpoint, timeout_seconds=2.0).send(
        ["exec highlighter_session", 'playdemo "match.dem"']
    )
    worker.join(timeout=5)
    server.close()

    assert sent is True
    assert received[0] == "PASS hunter2"
    assert received[1] == "exec highlighter_session"
    assert received[2] == 'playdemo "match.dem"'


def test_a_console_session_accepts_another_demo(tmp_path):
    session = make_session(tmp_path, channel="netcon", netcon_port=4242)

    assert session.uses_netcon is True
    assert session.fits(make_plan("other.dem"), RecordingConfig()) is True


def test_a_demo_session_still_needs_the_same_demo(tmp_path):
    session = make_session(tmp_path, channel="demo")

    assert session.uses_netcon is False
    assert session.fits(make_plan("other.dem"), RecordingConfig()) is False


def test_a_console_session_still_needs_the_same_resolution(tmp_path):
    session = make_session(tmp_path, channel="netcon", netcon_port=4242)

    assert session.fits(make_plan(), RecordingConfig(width=2560)) is False


def test_the_console_password_never_leaves_the_marker(tmp_path):
    session = make_session(tmp_path, channel="netcon", netcon_port=4242, netcon_password="secret")

    assert "netconPassword" not in session.to_mapping()
    assert session.to_mapping()["demoClosed"] is True
    assert session.to_marker()["netconPassword"] == "secret"


def test_a_saved_console_session_reads_its_endpoint_back(tmp_path):
    store = WarmSessionStore(tmp_path)
    store._write(
        make_session(tmp_path, channel="netcon", netcon_port=4242, netcon_password="secret")
    )

    loaded = store.load()

    assert loaded.endpoint.port == 4242
    assert loaded.endpoint.password == "secret"


def test_the_finish_script_can_be_rewritten_after_launch(tmp_path):
    config_directory = tmp_path / "cfg"
    config_directory.mkdir()
    writer = ScriptWriter(config_directory)
    writer.write(build(RecordingConfig(keep_game_open=True), make_plan()))

    writer.replace(FINISH_SCRIPT_NAME, MirvScriptBuilder.disconnect_script())

    assert (config_directory / f"{FINISH_SCRIPT_NAME}.cfg").read_text() == "mirv_cmd clear\ndisconnect\n"


def test_a_marker_from_an_older_build_is_thrown_away(tmp_path):
    marker = tmp_path / "warm_session.json"
    marker.write_text(json.dumps({"version": 1, "pid": 1}), encoding="utf-8")
    store = WarmSessionStore(tmp_path)

    assert store.live() is None
    assert not marker.exists()


def test_settling_returns_once_the_takes_stop_growing(tmp_path):
    watcher = TakeWatcher(
        make_plan(), tmp_path, settle_seconds=0.03, stall_seconds=5.0, poll_interval_seconds=0.01
    )
    write_take(tmp_path, "c1", "s01", 128)

    progress = watcher.settle(timeout_seconds=5.0)

    assert progress.bytes_written == 128


def test_settling_waits_while_a_take_is_still_being_written(tmp_path):
    import threading

    watcher = TakeWatcher(
        make_plan(), tmp_path, settle_seconds=0.05, stall_seconds=5.0, poll_interval_seconds=0.01
    )
    write_take(tmp_path, "c1", "s01", 64)
    stop = threading.Event()

    def keep_writing() -> None:
        size = 64
        while not stop.is_set() and size < 640:
            size += 64
            write_take(tmp_path, "c1", "s01", size)
            time.sleep(0.01)

    worker = threading.Thread(target=keep_writing, daemon=True)
    worker.start()
    progress = watcher.settle(timeout_seconds=5.0)
    stop.set()
    worker.join(timeout=2)

    assert progress.bytes_written == 640


def test_settling_gives_up_when_the_writing_never_stops(tmp_path):
    import threading

    watcher = TakeWatcher(
        make_plan(), tmp_path, settle_seconds=1.0, stall_seconds=5.0, poll_interval_seconds=0.01
    )
    stop = threading.Event()

    def keep_writing() -> None:
        size = 64
        while not stop.is_set():
            size += 64
            write_take(tmp_path, "c1", "s01", size)
            time.sleep(0.01)

    worker = threading.Thread(target=keep_writing, daemon=True)
    worker.start()
    progress = watcher.settle(timeout_seconds=0.2)
    stop.set()
    worker.join(timeout=2)

    assert progress.bytes_written > 0


def test_settling_an_empty_take_directory_does_not_hang(tmp_path):
    watcher = TakeWatcher(
        make_plan(), tmp_path, settle_seconds=0.03, stall_seconds=5.0, poll_interval_seconds=0.01
    )

    progress = watcher.settle(timeout_seconds=5.0)

    assert progress.bytes_written == 0


def test_the_quit_waits_a_few_seconds_after_the_last_take():
    bundle = build(RecordingConfig(), make_plan())
    lines = script(bundle, "highlighter_c01_s01_end").splitlines()

    assert lines[0] == "mirv_streams record end"
    assert lines[1].startswith("mirv_cmd addAtTick ")
    assert lines[1].endswith(" quit")


def test_the_quit_is_scheduled_after_the_recording_stops():
    bundle = build(RecordingConfig(), make_plan())
    quit_tick = int(script(bundle, "highlighter_c01_s01_end").splitlines()[1].split()[2])

    assert quit_tick > 10_600


def test_nothing_quits_when_the_game_should_stay_open():
    bundle = build(RecordingConfig(close_game_when_done=False), make_plan())

    assert script(bundle, "highlighter_c01_s01_end").strip() == "mirv_streams record end"


def test_a_kept_open_game_never_schedules_a_quit():
    bundle = build(RecordingConfig(keep_game_open=True), make_plan())

    assert "quit" not in script(bundle, "highlighter_c01_s01_end")


def test_the_watcher_lets_the_takes_finish_after_the_game_closes(tmp_path):
    import threading

    watcher = TakeWatcher(
        make_plan(), tmp_path, settle_seconds=0.05, stall_seconds=5.0, poll_interval_seconds=0.01
    )
    write_take(tmp_path, "c1", "s01", 64)
    stop = threading.Event()

    def finish_writing() -> None:
        size = 64
        while not stop.is_set() and size < 512:
            size += 64
            write_take(tmp_path, "c1", "s01", size)
            time.sleep(0.01)

    worker = threading.Thread(target=finish_writing, daemon=True)
    worker.start()
    progress = watcher.wait(timeout_seconds=5.0, is_alive=lambda: False)
    stop.set()
    worker.join(timeout=2)

    assert progress.bytes_written == 512
