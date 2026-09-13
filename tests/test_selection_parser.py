from __future__ import annotations

import pytest

from highlighter.presentation.selection_parser import SelectionParser


@pytest.fixture
def parser() -> SelectionParser:
    return SelectionParser(maximum_index=10)


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("1", [1]),
        ("1,3,5", [1, 3, 5]),
        ("1 3 5", [1, 3, 5]),
        ("2-5", [2, 3, 4, 5]),
        ("5-2", [2, 3, 4, 5]),
        ("1,3-5,9", [1, 3, 4, 5, 9]),
        ("3,3,3", [3]),
        ("  4 , 2  ", [2, 4]),
    ],
)
def test_parses_index_expressions(parser: SelectionParser, expression: str, expected: list[int]):
    assert parser.parse(expression) == expected


@pytest.mark.parametrize("expression", ["all", "ALL", "*", "все"])
def test_all_keywords_select_everything(parser: SelectionParser, expression: str):
    assert parser.parse(expression) == list(range(1, 11))


@pytest.mark.parametrize("expression", ["", "   ", "none", "q", "quit", "отмена"])
def test_cancel_keywords_select_nothing(parser: SelectionParser, expression: str):
    assert parser.parse(expression) == []


def test_out_of_range_values_are_dropped_from_ranges(parser: SelectionParser):
    assert parser.parse("8-14") == [8, 9, 10]


@pytest.mark.parametrize("expression", ["abc", "1..3", "12", "0"])
def test_invalid_tokens_raise(parser: SelectionParser, expression: str):
    with pytest.raises(ValueError):
        parser.parse(expression)
