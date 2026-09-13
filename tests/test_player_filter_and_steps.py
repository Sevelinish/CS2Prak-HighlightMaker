from __future__ import annotations

import io

import pytest
from conftest import make_kill, make_player, make_roster, make_round
from rich.console import Console

from highlighter.config.schema import DetectionConfig
from highlighter.detection.engine import HighlightEngine
from highlighter.detection.player_filter import PlayerNotFoundError, PlayerResolver
from highlighter.presentation.steps import StepReporter


@pytest.fixture
def populated(match, terrorists, counter_terrorists):
    roster = make_roster(terrorists, counter_terrorists)
    for number, hero in enumerate(terrorists[:3], start=1):
        match.rounds.append(
            make_round(
                number=number,
                roster=roster,
                freeze_end_tick=number * 10_000,
                end_tick=number * 10_000 + 8_000,
                kills=[
                    make_kill(number * 10_000 + 100, hero, counter_terrorists[0],
                              round_number=number),
                    make_kill(number * 10_000 + 200, hero, counter_terrorists[1],
                              round_number=number),
                    make_kill(number * 10_000 + 300, hero, counter_terrorists[2],
                              round_number=number),
                ],
            )
        )
    for player in terrorists + counter_terrorists:
        match.players[player.steam_id64] = player
    return match


def detect(match, only=None):
    return HighlightEngine(DetectionConfig(minimum_score=1.0)).detect(match, only)


def test_without_a_filter_every_player_is_scanned(populated):
    assert len({item.player.steam_id64 for item in detect(populated)}) == 3


def test_filter_keeps_only_the_requested_player(populated, terrorists):
    highlights = detect(populated, terrorists[0].steam_id64)

    assert highlights
    assert {item.player.steam_id64 for item in highlights} == {terrorists[0].steam_id64}


def test_filter_applies_before_the_maximum_limit(populated, terrorists):
    settings = DetectionConfig(minimum_score=1.0, maximum_highlights=1)
    engine = HighlightEngine(settings)

    highlights = engine.detect(populated, terrorists[2].steam_id64)

    assert len(highlights) == 1
    assert highlights[0].player.steam_id64 == terrorists[2].steam_id64


def test_resolver_finds_an_exact_name(populated, terrorists):
    assert PlayerResolver(populated).resolve(terrorists[0].name) == terrorists[0]


def test_resolver_ignores_case(populated, terrorists):
    assert PlayerResolver(populated).resolve(terrorists[0].name.upper()) == terrorists[0]


def test_resolver_accepts_a_steam_id(populated, terrorists):
    assert PlayerResolver(populated).resolve(str(terrorists[0].steam_id64)) == terrorists[0]


def test_resolver_accepts_a_unique_partial_name(populated):
    populated.players[999] = make_player(99, "uniquename")

    assert PlayerResolver(populated).resolve("uniquena").name == "uniquename"


def test_ambiguous_query_lists_the_candidates(populated):
    with pytest.raises(PlayerNotFoundError, match="matches several players"):
        PlayerResolver(populated).resolve("player")


def test_unknown_name_lists_the_roster(populated):
    with pytest.raises(PlayerNotFoundError, match="Players:"):
        PlayerResolver(populated).resolve("nobody")


def test_unknown_steam_id_is_reported(populated):
    with pytest.raises(PlayerNotFoundError, match="not in this demo"):
        PlayerResolver(populated).resolve("76561190000000000")


def test_empty_query_is_rejected(populated):
    with pytest.raises(PlayerNotFoundError):
        PlayerResolver(populated).resolve("   ")


def render_steps() -> str:
    buffer = io.StringIO()
    console = Console(file=buffer, width=100, no_color=True, highlight=False)
    reporter = StepReporter(console, total=3)

    reporter.begin("Launching Counter-Strike 2")
    reporter.detail("encoder h264_nvenc")
    reporter.done("game is up")
    reporter.begin("Recording 2 clip(s)")
    reporter.done("2 of 2 clips captured")
    with reporter.step("Saving videos"):
        pass
    return buffer.getvalue()


def test_steps_are_numbered_against_the_total():
    output = render_steps()

    assert "1/3 Launching Counter-Strike 2" in output
    assert "2/3 Recording 2 clip(s)" in output
    assert "3/3 Saving videos" in output


def test_steps_show_details_and_completion():
    output = render_steps()

    assert "encoder h264_nvenc" in output
    assert "game is up" in output
    assert output.count("✓") == 3


def test_a_failing_step_is_marked():
    buffer = io.StringIO()
    reporter = StepReporter(Console(file=buffer, width=100, no_color=True), total=1)

    with pytest.raises(RuntimeError):
        with reporter.step("Recording"):
            raise RuntimeError("boom")

    assert "✗" in buffer.getvalue()


def test_done_without_an_open_step_prints_nothing():
    buffer = io.StringIO()
    StepReporter(Console(file=buffer, width=100, no_color=True), total=1).done("x")

    assert buffer.getvalue() == ""


class LegacyStream(io.StringIO):
    encoding = "cp866"


class Utf8Stream(io.StringIO):
    encoding = "utf-8"


def test_marks_fall_back_to_ascii_on_a_legacy_console():
    stream = LegacyStream()
    reporter = StepReporter(Console(file=stream, width=100, no_color=True), total=1)

    reporter.begin("Recording")
    reporter.done("ok")
    output = stream.getvalue()

    assert "OK" in output
    assert "✓" not in output
    output.encode("cp866")


def test_marks_stay_unicode_on_a_utf8_console():
    stream = Utf8Stream()
    reporter = StepReporter(Console(file=stream, width=100, no_color=True), total=1)

    reporter.begin("Recording")
    reporter.done()

    assert "✓" in stream.getvalue()


def test_step_total_covers_the_optional_player_lookup():
    from highlighter.application import BASE_STEPS, Application

    without = Application.__new__(Application)
    without._player_query = None
    with_player = Application.__new__(Application)
    with_player._player_query = "s1mple"

    assert without._total_steps() == BASE_STEPS
    assert with_player._total_steps() == BASE_STEPS + 1
