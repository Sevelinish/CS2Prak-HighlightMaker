from __future__ import annotations

import json
import re
from pathlib import Path

from highlighter.config.schema import ApplicationConfig
from highlighter.editor.buffer import TextBuffer
from highlighter.editor.config_editor import ConfigFile, StraySettingFinder
from highlighter.editor.editor import TextEditor
from highlighter.editor.highlight import JsonHighlighter
from highlighter.editor.history import EditHistory
from highlighter.editor.screen import EditorScreen, Status
from highlighter.editor.theme import Ink, Palette
from highlighter.editor.validator import JsonValidator
from highlighter.editor.viewport import Viewport
from highlighter.shell.keys import Key, KeyPress

ESCAPE_PATTERN = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
SAMPLE = '{\n  "fps": 60,\n  "debug": false\n}'


class FakeTerminal:
    def __init__(self, width: int = 80, height: int = 12) -> None:
        self.width = width
        self.height = height
        self.frames: list[str] = []

    def write(self, text: str) -> None:
        self.frames.append(text)

    def flush(self) -> None:
        return None

    def column(self, index: int) -> str:
        return ""

    @staticmethod
    def position(row: int, column: int) -> str:
        return f"<{row},{column}>"

    @property
    def last(self) -> str:
        return self.frames[-1] if self.frames else ""


class ScriptedReader:
    def __init__(self, presses: list[KeyPress]) -> None:
        self._presses = list(presses)

    def read(self) -> KeyPress:
        if not self._presses:
            raise AssertionError("the editor asked for a key the script does not have")
        return self._presses.pop(0)


class Sink:
    def __init__(self) -> None:
        self.written: list[str] = []

    def __call__(self, text: str) -> None:
        self.written.append(text)


def typed(text: str) -> list[KeyPress]:
    return [KeyPress.of(character) for character in text]


def plain(frame: str) -> str:
    return ESCAPE_PATTERN.sub("", frame)


def build_screen(terminal: FakeTerminal | None = None) -> EditorScreen:
    return EditorScreen(
        terminal=terminal or FakeTerminal(), palette=Palette(coloured=False)
    )


def run_editor(
    presses: list[KeyPress],
    text: str = SAMPLE,
    writer: Sink | None = None,
    validator: JsonValidator | None = None,
    terminal: FakeTerminal | None = None,
):
    editor = TextEditor(
        reader=ScriptedReader(presses),
        screen=build_screen(terminal),
        title="config.json",
        validator=validator,
        writer=writer,
    )
    return editor.edit(text)


def test_text_becomes_lines():
    assert TextBuffer.of("a\nb").lines == ("a", "b")


def test_a_tab_in_the_file_becomes_spaces():
    assert TextBuffer.of("\tx").lines == ("  x",)


def test_typing_lands_at_the_cursor():
    buffer = TextBuffer.of("ac").move_to(0, 1).insert("b")

    assert buffer.line == "abc"
    assert buffer.column == 2


def test_enter_keeps_the_indentation():
    buffer = TextBuffer.of('  "fps": 60,').move_to(0, 12).split_line()

    assert buffer.lines == ('  "fps": 60,', "  ")
    assert (buffer.row, buffer.column) == (1, 2)


def test_backspace_removes_a_whole_indent_step():
    buffer = TextBuffer.of("    x").move_to(0, 4).backspace()

    assert buffer.line == "  x"


def test_backspace_inside_text_removes_one_character():
    buffer = TextBuffer.of("abc").move_to(0, 3).backspace()

    assert buffer.line == "ab"


def test_backspace_at_the_start_joins_the_line_above():
    buffer = TextBuffer.of("ab\ncd").move_to(1, 0).backspace()

    assert buffer.lines == ("abcd",)
    assert (buffer.row, buffer.column) == (0, 2)


def test_delete_at_the_end_pulls_the_next_line_up():
    buffer = TextBuffer.of("ab\ncd").move_to(0, 2).delete()

    assert buffer.lines == ("abcd",)


def test_cut_to_end_keeps_the_head():
    buffer = TextBuffer.of("abcdef").move_to(0, 3).delete_to_end()

    assert buffer.lines == ("abc",)


def test_deleting_a_word_stops_at_the_quote():
    buffer = TextBuffer.of('  "fps": 60').move_to(0, 11).delete_word_before()

    assert buffer.line == '  "fps": '


def test_going_down_remembers_the_column():
    buffer = TextBuffer.of("longer line\nab\nlonger line").move_to(0, 10)

    walked = buffer.move_down().move_down()

    assert (walked.row, walked.column) == (2, 10)


def test_going_down_clamps_on_a_short_line():
    buffer = TextBuffer.of("longer line\nab").move_to(0, 10).move_down()

    assert (buffer.row, buffer.column) == (1, 2)


def test_home_toggles_between_the_indent_and_the_margin():
    buffer = TextBuffer.of("  text").move_to(0, 6)

    first = buffer.move_home()
    second = first.move_home()

    assert first.column == 2
    assert second.column == 0


def test_a_page_moves_by_the_window():
    buffer = TextBuffer.of("\n".join(str(index) for index in range(40)))

    assert buffer.move_page_down(10).row == 10
    assert buffer.move_page_down(10).move_page_up(10).row == 0


def test_moving_past_the_end_stops_there():
    buffer = TextBuffer.of("a\nb").move_to(99, 99)

    assert (buffer.row, buffer.column) == (1, 1)


def test_the_history_walks_back_and_forward():
    first = TextBuffer.of("a")
    second = TextBuffer.of("ab")
    history = EditHistory(first)
    history.record(second)

    assert history.undo(second).text == "a"
    assert history.redo(first).text == "ab"


def test_moving_the_cursor_is_not_a_step():
    start = TextBuffer.of("abc")
    history = EditHistory(start)

    history.record(start.move_to(0, 2))

    assert history.can_undo is False


def test_a_new_edit_drops_what_was_undone():
    history = EditHistory(TextBuffer.of("a"))
    history.record(TextBuffer.of("ab"))
    history.undo(TextBuffer.of("ab"))
    history.record(TextBuffer.of("ac"))

    assert history.can_redo is False


def test_the_history_is_bounded():
    history = EditHistory(TextBuffer.of(""), depth=3)
    for index in range(10):
        history.record(TextBuffer.of("x" * (index + 1)))

    assert history.can_undo is True


def test_the_window_follows_the_cursor_down():
    buffer = TextBuffer.of("\n".join(str(index) for index in range(40))).move_to(25)
    viewport = Viewport(rows=10, columns=40).following(buffer)

    assert viewport.top == 16
    assert buffer.row in viewport.visible_rows(buffer)


def test_the_window_follows_the_cursor_back_up():
    buffer = TextBuffer.of("\n".join(str(index) for index in range(40)))
    viewport = Viewport(top=20, rows=10, columns=40).following(buffer.move_to(3))

    assert viewport.top == 3


def test_the_window_never_hangs_past_the_last_line():
    buffer = TextBuffer.of("a\nb\nc")
    viewport = Viewport(top=30, rows=10, columns=40).following(buffer)

    assert viewport.top == 0


def test_a_long_line_scrolls_sideways():
    buffer = TextBuffer.of("x" * 200).move_to(0, 150)
    viewport = Viewport(rows=10, columns=40).following(buffer)

    assert viewport.left > 0
    assert viewport.screen_column(buffer.column) < 40


def test_a_key_and_a_value_are_told_apart():
    spans = JsonHighlighter().spans('  "fps": "sixty"')
    inks = {span.text: span.ink for span in spans}

    assert inks['"fps"'] is Ink.KEY
    assert inks['"sixty"'] is Ink.STRING


def test_numbers_and_literals_are_marked():
    inks = {span.text: span.ink for span in JsonHighlighter().spans("[1.5, true, null]")}

    assert inks["1.5"] is Ink.NUMBER
    assert inks["true"] is Ink.LITERAL
    assert inks["null"] is Ink.LITERAL


def test_braces_are_punctuation():
    assert JsonHighlighter().spans("{")[0].ink is Ink.PUNCTUATION


def test_a_half_typed_string_does_not_break_the_painter():
    spans = JsonHighlighter().spans('  "fp')

    assert "".join(span.text for span in spans) == '  "fp'


def test_the_painted_line_is_the_same_text():
    line = '  "outputDirectory": "Highlighter",'

    assert "".join(span.text for span in JsonHighlighter().spans(line)) == line


def test_good_json_passes():
    assert JsonValidator().check(SAMPLE).ok is True


def test_broken_json_points_at_the_line():
    verdict = JsonValidator().check('{\n  "fps": 60\n  "debug": false\n}')

    assert verdict.ok is False
    assert verdict.row == 2


def test_a_list_is_not_a_config():
    assert JsonValidator().check("[1, 2]").ok is False


def test_a_wrong_kind_of_value_is_caught():
    validator = JsonValidator(ApplicationConfig.from_mapping)

    verdict = validator.check('{"recording": {"fps": "sixty"}}')

    assert verdict.ok is False


def test_the_shape_check_accepts_a_real_config():
    validator = JsonValidator(ApplicationConfig.from_mapping)

    assert validator.check(json.dumps(ApplicationConfig().to_mapping())).ok is True


def test_the_title_bar_says_whether_there_are_changes():
    screen = build_screen()
    buffer = TextBuffer.of(SAMPLE)
    viewport = screen.fitted(Viewport(), buffer)

    modified = plain(screen.render(buffer, viewport, Status(modified=True)))
    saved = plain(screen.render(buffer, viewport, Status(modified=False)))

    assert "modified" in modified
    assert "saved" in saved


def test_every_line_gets_its_number():
    screen = build_screen()
    buffer = TextBuffer.of(SAMPLE)

    frame = plain(screen.render(buffer, screen.fitted(Viewport(), buffer), Status()))

    assert "1 | {" in frame
    assert '2 |   "fps": 60,' in frame


def test_the_cursor_sits_where_the_caret_is():
    terminal = FakeTerminal()
    screen = build_screen(terminal)
    buffer = TextBuffer.of(SAMPLE).move_to(1, 4)
    viewport = screen.fitted(Viewport(), buffer)

    frame = screen.render(buffer, viewport, Status())

    assert frame.rstrip().endswith("<3,9>\x1b[?25h")


def test_the_place_in_the_file_is_shown():
    screen = build_screen()
    buffer = TextBuffer.of(SAMPLE).move_to(2, 3)

    frame = plain(screen.render(buffer, screen.fitted(Viewport(), buffer), Status()))

    assert "line 3, column 4" in frame


def test_typing_and_saving_writes_the_text():
    sink = Sink()

    outcome = run_editor(
        [KeyPress(Key.DOCUMENT_END), *typed(" "), KeyPress(Key.SAVE), KeyPress(Key.EXIT)],
        writer=sink,
    )

    assert outcome.saved is True
    assert sink.written == [SAMPLE + " "]


def test_nothing_is_written_when_nothing_changed():
    sink = Sink()

    outcome = run_editor([KeyPress(Key.SAVE), KeyPress(Key.EXIT)], writer=sink)

    assert sink.written == []
    assert outcome.saved is False


def test_broken_json_is_never_written():
    sink = Sink()
    terminal = FakeTerminal()

    run_editor(
        [KeyPress(Key.DOCUMENT_END), *typed("{"), KeyPress(Key.SAVE), KeyPress(Key.EXIT), *typed("n")],
        writer=sink,
        validator=JsonValidator(),
        terminal=terminal,
    )

    shown = plain("".join(terminal.frames))

    assert sink.written == []
    assert JsonValidator().check(SAMPLE + "{").message in shown


def test_leaving_with_changes_asks_first():
    sink = Sink()
    terminal = FakeTerminal()

    run_editor(
        [*typed("x"), KeyPress(Key.EXIT), *typed("n")], writer=sink, terminal=terminal
    )

    assert sink.written == []


def test_answering_yes_saves_on_the_way_out():
    sink = Sink()

    outcome = run_editor([*typed("x"), KeyPress(Key.EXIT), *typed("y")], writer=sink)

    assert outcome.saved is True
    assert sink.written == ["x" + SAMPLE]


def test_a_stray_key_at_the_question_keeps_editing():
    sink = Sink()

    outcome = run_editor(
        [*typed("x"), KeyPress(Key.EXIT), KeyPress(Key.ESCAPE), KeyPress(Key.EXIT), *typed("n")],
        writer=sink,
    )

    assert outcome.saved is False
    assert sink.written == []


def test_undo_takes_the_typing_back():
    outcome = run_editor([*typed("xy"), KeyPress(Key.UNDO), KeyPress(Key.UNDO), KeyPress(Key.EXIT), *typed("n")])

    assert outcome.text == SAMPLE


def test_redo_puts_it_back():
    presses = [
        *typed("x"),
        KeyPress(Key.UNDO),
        KeyPress(Key.REDO),
        KeyPress(Key.EXIT),
        *typed("n"),
    ]

    assert run_editor(presses).text == "x" + SAMPLE


def test_tab_inserts_two_spaces():
    outcome = run_editor([KeyPress(Key.TAB), KeyPress(Key.EXIT), *typed("n")])

    assert outcome.text.startswith("  {")


def test_the_file_round_trips(tmp_path: Path):
    path = tmp_path / "config.json"
    body = SAMPLE + chr(10)
    path.write_bytes(body.encode("utf-8"))
    handle = ConfigFile(path)

    text = handle.read()
    handle.write(text)

    assert text == body
    assert path.read_bytes() == body.encode("utf-8")


def test_windows_line_endings_are_kept(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_bytes((SAMPLE + chr(10)).replace(chr(10), chr(13) + chr(10)).encode("utf-8"))
    handle = ConfigFile(path)

    handle.write(handle.read())

    assert (chr(13) + chr(10)).encode("utf-8") in path.read_bytes()


def test_saving_leaves_no_half_written_file(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text(SAMPLE, encoding="utf-8")
    ConfigFile(path).write("{}")

    assert [item.name for item in tmp_path.iterdir()] == ["config.json"]


def test_a_missing_newline_is_added(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_bytes(SAMPLE.encode("utf-8"))
    handle = ConfigFile(path)
    handle.read()
    handle.write("{}")

    assert path.read_bytes() == ("{}" + chr(10)).encode("utf-8")


def test_a_setting_the_schema_does_not_know_is_found():
    raw = ApplicationConfig().to_mapping()
    raw["madeUp"] = 1
    raw["recording"]["alsoMadeUp"] = 2

    assert set(StraySettingFinder().find(raw)) == {"madeUp", "recording.alsoMadeUp"}


def test_a_clean_config_has_no_strays():
    assert StraySettingFinder().find(ApplicationConfig().to_mapping()) == ()
