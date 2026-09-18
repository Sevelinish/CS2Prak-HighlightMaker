from __future__ import annotations

import os
from pathlib import Path

import pytest

from highlighter.cli import CommandLine, CommandLineError, CommandLineStop
from highlighter.shell.context import LineContext
from highlighter.shell.document import Document
from highlighter.shell.grammar import Grammar
from highlighter.shell.history import CommandHistory
from highlighter.shell.keys import Key, KeyDecoder, KeyPress
from highlighter.shell.launcher import ShellLauncher
from highlighter.shell.layout import LineLayout
from highlighter.shell.prompt import LinePrompt
from highlighter.shell.reader import WindowsKeyReader
from highlighter.shell.renderer import LineRenderer
from highlighter.shell.router import CommandRouter
from highlighter.shell.runner import ShellResult
from highlighter.shell.suggester import Suggester, Suggestion
from highlighter.shell.terminal import Terminal, TerminalCapabilities
from highlighter.shell.tokens import Lexer

DEMOS = ("mirage17.dem", "mirage18.dem", "nuke04.dem")
SHELL_ONLY_FLAGS = {"-shell", "--shell", "-no-shell", "--no-shell"}


def at_end(text: str) -> Document:
    return Document(text=text, cursor=len(text))


def ghost_for(text: str, demos: tuple[str, ...] = DEMOS) -> Suggestion:
    return Suggester(demos=lambda: demos).suggest(at_end(text))


class ScriptedReader:
    def __init__(self, presses: list[KeyPress]) -> None:
        self._presses = list(presses)

    def read(self) -> KeyPress:
        if not self._presses:
            return KeyPress(Key.END_OF_INPUT)
        return self._presses.pop(0)


class SilentRenderer:
    def __init__(self) -> None:
        self.settled: list[str] = []
        self.cleared = 0

    def render(self, document: Document, suggestion: Suggestion) -> None:
        return None

    def settle(self, document: Document) -> None:
        self.settled.append(document.text)

    def clear_screen(self) -> None:
        self.cleared += 1


def typed(text: str) -> list[KeyPress]:
    return [KeyPress.of(character) for character in text]


def run_prompt(presses: list[KeyPress], demos: tuple[str, ...] = DEMOS) -> str | None:
    return LinePrompt(
        reader=ScriptedReader(presses),
        renderer=SilentRenderer(),
        suggester=Suggester(demos=lambda: demos),
    ).read()


def test_a_quoted_path_stays_one_token():
    assert Lexer.argv('"C:/my demos/a.dem" -p s1mple') == [
        "C:/my demos/a.dem",
        "-p",
        "s1mple",
    ]


def test_token_positions_point_back_at_the_line():
    tokens = Lexer.split("match.dem -p s1mple")

    assert [(token.text, token.start) for token in tokens] == [
        ("match.dem", 0),
        ("-p", 10),
        ("s1mple", 13),
    ]


def test_a_name_starting_with_a_dash_is_a_flag_shaped_token():
    assert Lexer.split("-n1clxe")[0].is_flag is True


def test_the_document_edits_around_the_cursor():
    document = Document(text="match.dem", cursor=5).insert("X")

    assert document.text == "matchX.dem"
    assert document.cursor == 6


def test_deleting_a_word_stops_at_the_separator():
    document = at_end("match.dem -p s1mple").delete_word_before()

    assert document.text == "match.dem -p "


def test_replacing_a_range_leaves_the_cursor_after_the_new_text():
    document = at_end("mir").replace_range(0, 3, "mirage17.dem")

    assert document.text == "mirage17.dem"
    assert document.cursor == len("mirage17.dem")


def test_the_context_knows_the_word_being_typed():
    context = LineContext.of(at_end("match.dem -p s1m"))

    assert context.word == "s1m"
    assert context.preceding == "-p"
    assert context.is_first_word is False


def test_a_trailing_space_opens_a_new_word():
    context = LineContext.of(at_end("match.dem -p "))

    assert context.word == ""
    assert context.preceding == "-p"


def test_a_half_typed_flag_is_completed():
    suggestion = ghost_for("-f")

    assert suggestion.completion == "ly"
    assert suggestion.has_completion is True


def test_a_flag_waiting_for_a_value_shows_the_placeholder():
    suggestion = ghost_for("-p")

    assert suggestion.completion == ""
    assert suggestion.ghost == " <nickname>"


def test_the_placeholder_stays_after_the_space():
    assert ghost_for("-p ").ghost == "<nickname>"


def test_a_player_name_is_never_completed():
    assert ghost_for("-p s1m").has_completion is False


def test_a_dashed_player_name_is_not_read_as_a_flag():
    assert ghost_for("match.dem -p -n1c").has_completion is False


def test_modes_are_completed_from_the_real_list():
    assert ghost_for("-m nades_").completion == "smoke"


def test_a_mode_is_asked_for_by_name():
    suggestion = ghost_for("-m ")

    assert suggestion.ghost == "<mode>"
    assert "highlights" in suggestion.hint


def test_demo_names_are_completed():
    assert ghost_for("mir").completion == "age17.dem"


def test_an_empty_line_asks_for_a_demo():
    assert ghost_for("").ghost == "<demo>"


def test_a_flag_already_typed_is_not_offered_again():
    offered = [item.text for item in ghost_for("match.dem -fly -").candidates]

    assert "-fly" not in offered


def test_an_unknown_flag_says_so():
    assert ghost_for("-zzz").hint == "no flag starts like that"


def test_the_second_word_is_not_a_demo():
    assert ghost_for("match.dem mir").has_completion is False


def test_a_shell_word_is_completed_before_a_demo():
    assert ghost_for("he").completion == "lp"


def test_history_completes_a_whole_line():
    history = CommandHistory()
    history.remember("mirage17.dem -m nades_smoke -fly")

    suggester = Suggester(demos=lambda: (), history=history)

    assert suggester.suggest(at_end("mirage17.dem -m")).completion == (
        " nades_smoke -fly"
    )


def test_history_walks_back_and_forward():
    history = CommandHistory()
    history.remember("first")
    history.remember("second")

    assert history.previous("draft") == "second"
    assert history.previous("draft") == "first"
    assert history.following() == "second"
    assert history.following() == "draft"


def test_history_survives_a_restart(tmp_path: Path):
    path = tmp_path / "shell_history.txt"
    CommandHistory(path).remember("mirage17.dem -enemy")

    assert CommandHistory(path).entries == ("mirage17.dem -enemy",)


def test_history_ignores_a_repeated_line():
    history = CommandHistory()
    history.remember("same")
    history.remember("same")

    assert history.entries == ("same",)


def test_the_layout_keeps_the_cursor_visible_on_a_long_line():
    document = at_end("x" * 200)
    line = LineLayout("> ", 40).build(document, Suggestion())

    assert len(line.text) <= 38
    assert line.cursor_column <= 39


def test_the_ghost_is_hidden_while_the_cursor_sits_inside_the_text():
    document = Document(text="match.dem", cursor=2)
    line = LineLayout("> ", 80).build(document, Suggestion(completion="xx"))

    assert line.ghost == ""


def test_the_hint_is_dropped_when_there_is_no_room():
    document = at_end("x" * 30)
    line = LineLayout("> ", 40).build(document, Suggestion(hint="a long explanation"))

    assert line.hint == ""


def test_typing_and_pressing_enter_returns_the_line():
    assert run_prompt([*typed("match.dem"), KeyPress(Key.ENTER)]) == "match.dem"


def test_the_right_arrow_takes_the_suggestion():
    line = run_prompt([*typed("-f"), KeyPress(Key.RIGHT), KeyPress(Key.ENTER)])

    assert line == "-fly"


def test_the_right_arrow_still_moves_inside_the_text():
    presses = [*typed("abc"), KeyPress(Key.HOME), KeyPress(Key.RIGHT), KeyPress.of("X")]
    line = run_prompt([*presses, KeyPress(Key.ENTER)], demos=())

    assert line == "aXbc"


def test_tab_walks_through_the_matches():
    line = run_prompt(
        [*typed("mir"), KeyPress(Key.TAB), KeyPress(Key.TAB), KeyPress(Key.ENTER)]
    )

    assert line == "mirage18.dem"


def test_tab_wraps_back_to_the_first_match():
    presses = [*typed("mir"), KeyPress(Key.TAB), KeyPress(Key.TAB), KeyPress(Key.TAB)]
    line = run_prompt([*presses, KeyPress(Key.ENTER)])

    assert line == "mirage17.dem"


def test_backspace_removes_the_last_character():
    line = run_prompt([*typed("abc"), KeyPress(Key.BACKSPACE), KeyPress(Key.ENTER)], demos=())

    assert line == "ab"


def test_ctrl_c_clears_a_line_it_does_not_leave():
    line = run_prompt(
        [*typed("abc"), KeyPress(Key.INTERRUPT), *typed("z"), KeyPress(Key.ENTER)],
        demos=(),
    )

    assert line == "z"


def test_ctrl_c_on_an_empty_line_ends_the_prompt():
    assert run_prompt([KeyPress(Key.INTERRUPT)], demos=()) is None


def test_the_end_of_input_ends_the_prompt():
    assert run_prompt([KeyPress(Key.END_OF_INPUT)], demos=()) is None


def test_the_grammar_covers_every_argument_the_parser_takes():
    grammar = Grammar()
    flags = {
        flag
        for action in CommandLine.build_parser()._actions
        for flag in action.option_strings
    }

    missing = {
        flag
        for flag in flags - SHELL_ONLY_FLAGS
        if grammar.option_for(flag) is None
    }

    assert missing == set()


def test_a_bad_argument_is_reported_instead_of_killing_the_process():
    with pytest.raises(CommandLineError):
        CommandLine.parse_quietly(["--nonsense"])


def test_asking_for_help_stops_the_parse_without_an_error():
    with pytest.raises(CommandLineStop):
        CommandLine.parse_quietly(["-h"])


def test_the_prompt_opens_when_the_exe_is_started_bare(monkeypatch):
    monkeypatch.setattr(TerminalCapabilities, "is_interactive", staticmethod(lambda: True))

    assert ShellLauncher.wanted([], CommandLine.parse([])) is True


def test_a_piped_console_never_opens_the_prompt(monkeypatch):
    monkeypatch.setattr(TerminalCapabilities, "is_interactive", staticmethod(lambda: False))

    assert ShellLauncher.wanted([], CommandLine.parse([])) is False


def test_arguments_run_straight_away():
    arguments = CommandLine.parse(["match.dem"])

    assert ShellLauncher.wanted(["match.dem"], arguments) is False


def test_the_prompt_can_be_forced():
    arguments = CommandLine.parse(["match.dem", "-shell"])

    assert ShellLauncher.wanted(["match.dem", "-shell"], arguments) is True


def test_the_prompt_can_be_refused():
    arguments = CommandLine.parse(["-no-shell"])

    assert ShellLauncher.wanted([], arguments) is False


def test_the_api_never_opens_the_prompt():
    arguments = CommandLine.parse(["--api", "stdio"])

    assert ShellLauncher.wanted([], arguments) is False


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, argv: list[str]) -> ShellResult:
        self.calls.append(list(argv))
        return ShellResult()


class StillCatalogue:
    def __init__(self) -> None:
        self.refreshed = 0

    def refresh(self) -> None:
        self.refreshed += 1

    def demos(self) -> tuple[Path, ...]:
        return ()

    def names(self) -> tuple[str, ...]:
        return ()


def build_router(runner: RecordingRunner, renderer: SilentRenderer | None = None):
    from rich.console import Console

    return CommandRouter(
        console=Console(file=open(os.devnull, "w", encoding="utf-8"), no_color=True),
        runner=runner,
        catalogue=StillCatalogue(),
        renderer=renderer or SilentRenderer(),
    )


def test_a_plain_line_goes_to_the_runner():
    runner = RecordingRunner()

    build_router(runner).route("match.dem -p s1mple")

    assert runner.calls == [["match.dem", "-p", "s1mple"]]


def test_run_is_stripped_before_the_arguments():
    runner = RecordingRunner()

    build_router(runner).route("run match.dem -enemy")

    assert runner.calls == [["match.dem", "-enemy"]]


def test_run_on_its_own_records_with_no_arguments():
    runner = RecordingRunner()

    build_router(runner).route("run")

    assert runner.calls == [[]]


def test_exit_asks_the_session_to_stop():
    assert build_router(RecordingRunner()).route("exit").should_exit is True


def test_quit_is_the_same_word():
    assert build_router(RecordingRunner()).route("quit").should_exit is True


def test_clear_wipes_the_screen_without_running_anything():
    runner = RecordingRunner()
    renderer = SilentRenderer()

    build_router(runner, renderer).route("cls")

    assert renderer.cleared == 1
    assert runner.calls == []


def test_an_empty_line_does_nothing():
    runner = RecordingRunner()

    result = build_router(runner).route("   ")

    assert runner.calls == []
    assert result.should_exit is False


ESCAPE = chr(27)
EXTENDED_PREFIX = chr(224)
CARRIAGE_RETURN = chr(13)
CTRL_C = chr(3)


class FakeSource:
    def __init__(self, characters: str) -> None:
        self._characters = list(characters)

    def __call__(self) -> str:
        return self._characters.pop(0)


class CapturingStream:
    def __init__(self) -> None:
        self.written: list[str] = []

    def write(self, text: str) -> None:
        self.written.append(text)

    def flush(self) -> None:
        return None

    @property
    def text(self) -> str:
        return "".join(self.written)


def test_an_arrow_key_arrives_as_a_movement():
    press = WindowsKeyReader(source=FakeSource(f"{EXTENDED_PREFIX}K")).read()

    assert press.key is Key.LEFT


def test_an_ordinary_letter_arrives_as_itself():
    press = WindowsKeyReader(source=FakeSource("a")).read()

    assert press.is_character is True
    assert press.character == "a"


def test_ctrl_c_arrives_as_an_interrupt():
    assert WindowsKeyReader(source=FakeSource(CTRL_C)).read().key is Key.INTERRUPT


def test_a_posix_arrow_sequence_is_understood():
    assert KeyDecoder.sequence("[D") is Key.LEFT


def test_the_rendered_line_carries_the_text_and_the_ghost():
    stream = CapturingStream()
    renderer = LineRenderer("> ", Terminal(stream))

    renderer.render(at_end("-f"), Suggestion(completion="ly", hint="follow it"))

    assert "> " in stream.text
    assert "-f" in stream.text
    assert "ly" in stream.text
    assert "follow it" in stream.text


def test_the_cursor_is_put_back_after_the_typed_text():
    stream = CapturingStream()
    renderer = LineRenderer("> ", Terminal(stream))

    renderer.render(at_end("-f"), Suggestion(completion="ly"))

    assert stream.text.endswith(f"{CARRIAGE_RETURN}{ESCAPE}[4C")
