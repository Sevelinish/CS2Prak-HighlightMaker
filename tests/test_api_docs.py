from __future__ import annotations

import re
from pathlib import Path

import pytest

from highlighter.api.contract import COMMAND_NAMES, HOST_APPLICATION, HOST_REPOSITORY
from highlighter.api.errors import ErrorCode

DOCUMENT = Path(__file__).resolve().parents[1] / "docs" / "API.md"
HEADING_PATTERN = re.compile(r"^### (?P<name>[a-z]+(?:\.[a-z]+)*)$", re.MULTILINE)
EM_DASH = "\u2014"
EN_DASH = "\u2013"


@pytest.fixture(scope="module")
def text() -> str:
    return DOCUMENT.read_text(encoding="utf-8")


def test_the_document_exists(text: str):
    assert text.strip()


def test_the_document_names_the_launcher_it_was_written_for(text: str):
    assert HOST_APPLICATION in text
    assert HOST_REPOSITORY in text


def test_every_command_has_its_own_section(text: str):
    documented = {match.group("name") for match in HEADING_PATTERN.finditer(text)}

    assert set(COMMAND_NAMES) <= documented


def test_no_section_documents_a_command_that_does_not_exist(text: str):
    documented = {match.group("name") for match in HEADING_PATTERN.finditer(text)}
    commands = {name for name in documented if "." in name or name in COMMAND_NAMES}

    assert commands <= set(COMMAND_NAMES)


def test_every_documented_error_code_is_real(text: str):
    documented = set(re.findall(r"^\| `([a-z_]+)` \| \d{3} \|", text, re.MULTILINE))
    known = {code.value for code in ErrorCode}

    assert documented
    assert documented <= known


def test_the_document_uses_no_long_dashes(text: str):
    assert EM_DASH not in text
    assert EN_DASH not in text


def test_the_readme_points_at_the_document():
    readme = (DOCUMENT.parents[1] / "README.md").read_text(encoding="utf-8")

    assert "docs/API.md" in readme
    assert EM_DASH not in readme
