from __future__ import annotations

import bz2
import gzip
import json
from pathlib import Path

import pytest

from highlighter.config.schema import ApplicationConfig
from highlighter.importing.archives import ArchiveError, DemoExtractor, DemoFile
from highlighter.importing.importer import DemoImporter, DemoSummary, ImportCandidate
from highlighter.importing.ledger import ImportLedger
from highlighter.importing.sources import DemoSourceLocator
from highlighter.infrastructure.paths import ApplicationPaths

PAYLOAD = b"PBDEMS2\x00fake demo bytes"


def importer_for(tmp_path: Path) -> DemoImporter:
    return DemoImporter(ApplicationPaths(tmp_path), ApplicationConfig(), None)


def test_a_plain_demo_is_not_an_archive(tmp_path: Path):
    demo = DemoFile(tmp_path / "match.dem")

    assert demo.is_archive is False
    assert demo.demo_name == "match"


def test_a_faceit_archive_keeps_its_demo_name(tmp_path: Path):
    demo = DemoFile(tmp_path / "1-9b7f-1-1.dem.zst")

    assert demo.is_archive is True
    assert demo.demo_name == "1-9b7f-1-1"


def test_gzip_and_bzip2_archives_are_recognised(tmp_path: Path):
    assert DemoFile(tmp_path / "a.dem.gz").is_archive is True
    assert DemoFile(tmp_path / "a.dem.bz2").is_archive is True


def test_a_gzip_archive_unpacks(tmp_path: Path):
    source = tmp_path / "match.dem.gz"
    with gzip.open(source, "wb") as sink:
        sink.write(PAYLOAD)

    unpacked = DemoExtractor().extract(DemoFile(source), tmp_path / "out" / "match.dem")

    assert unpacked.read_bytes() == PAYLOAD


def test_a_bzip2_archive_unpacks(tmp_path: Path):
    source = tmp_path / "match.dem.bz2"
    with bz2.open(source, "wb") as sink:
        sink.write(PAYLOAD)

    unpacked = DemoExtractor().extract(DemoFile(source), tmp_path / "out" / "match.dem")

    assert unpacked.read_bytes() == PAYLOAD


def test_a_zstd_archive_unpacks(tmp_path: Path):
    pyarrow = pytest.importorskip("pyarrow")
    source = tmp_path / "match.dem.zst"
    with pyarrow.CompressedOutputStream(pyarrow.OSFile(str(source), "wb"), "zstd") as sink:
        sink.write(PAYLOAD)

    unpacked = DemoExtractor().extract(DemoFile(source), tmp_path / "out" / "match.dem")

    assert unpacked.read_bytes() == PAYLOAD


def test_a_plain_demo_is_copied_not_moved(tmp_path: Path):
    source = tmp_path / "match.dem"
    source.write_bytes(PAYLOAD)

    DemoExtractor().extract(DemoFile(source), tmp_path / "out" / "match.dem")

    assert source.is_file()


def test_a_broken_archive_is_reported(tmp_path: Path):
    source = tmp_path / "match.dem.gz"
    source.write_bytes(b"not gzip at all")

    with pytest.raises(ArchiveError):
        DemoExtractor().extract(DemoFile(source), tmp_path / "out" / "match.dem")


def test_a_half_written_file_is_cleaned_up(tmp_path: Path):
    source = tmp_path / "match.dem.gz"
    source.write_bytes(b"not gzip at all")
    destination = tmp_path / "out" / "match.dem"

    with pytest.raises(ArchiveError):
        DemoExtractor().extract(DemoFile(source), destination)

    assert not destination.exists()


def test_a_name_with_forbidden_characters_is_cleaned():
    cleaned = DemoImporter.clean_name('my: match?/ "one"')

    assert cleaned == "my_ match__ _one_"
    assert not set(cleaned) & set('<>:"/\|?*')


def test_a_name_keeps_its_own_words():
    assert DemoImporter.clean_name("  mirage vs navi  ") == "mirage vs navi"


def test_a_name_loses_a_demo_suffix_the_user_typed():
    assert DemoImporter.clean_name("mirage1509.dem") == "mirage1509"


def test_an_empty_name_is_refused(tmp_path: Path):
    from highlighter.infrastructure.errors import HighlighterError

    candidate = ImportCandidate(
        source=DemoFile(tmp_path / "a.dem"),
        staged=tmp_path / "a.dem",
        summary=DemoSummary(map_name="de_dust2"),
    )
    candidate.staged.write_bytes(PAYLOAD)

    with pytest.raises(HighlighterError):
        importer_for(tmp_path).store(candidate, "   ")


def test_storing_puts_the_demo_in_the_demo_folder(tmp_path: Path):
    importer = importer_for(tmp_path)
    staged = tmp_path / "work" / "import" / "raw.dem"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(PAYLOAD)
    candidate = ImportCandidate(
        source=DemoFile(tmp_path / "raw.dem.zst"),
        staged=staged,
        summary=DemoSummary(map_name="de_dust2"),
    )

    destination = importer.store(candidate, "dust21509")

    assert destination == tmp_path / "demos" / "dust21509.dem"
    assert destination.read_bytes() == PAYLOAD
    assert not staged.exists()


def test_a_name_that_is_taken_gets_a_number(tmp_path: Path):
    importer = importer_for(tmp_path)
    (tmp_path / "demos").mkdir()
    (tmp_path / "demos" / "dust2.dem").write_bytes(b"older")

    staged = tmp_path / "work" / "import" / "raw.dem"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(PAYLOAD)
    candidate = ImportCandidate(
        source=DemoFile(tmp_path / "raw.dem"),
        staged=staged,
        summary=DemoSummary(map_name="de_dust2"),
    )

    destination = importer.store(candidate, "dust2")

    assert destination.name == "dust2_2.dem"
    assert (tmp_path / "demos" / "dust2.dem").read_bytes() == b"older"


def test_an_imported_demo_is_not_offered_again(tmp_path: Path):
    source = tmp_path / "raw.dem"
    source.write_bytes(PAYLOAD)
    ledger = ImportLedger(tmp_path / "work")
    demo = DemoFile(source)

    assert ledger.knows(demo) is False
    ledger.remember(demo, "dust2.dem", "de_dust2", 1.0)

    assert ImportLedger(tmp_path / "work").knows(demo) is True


def test_a_skipped_demo_is_not_offered_again(tmp_path: Path):
    importer = importer_for(tmp_path)
    source = tmp_path / "raw.dem"
    source.write_bytes(PAYLOAD)
    staged = tmp_path / "work" / "import" / "raw.dem"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(PAYLOAD)
    candidate = ImportCandidate(
        source=DemoFile(source), staged=staged, summary=DemoSummary(map_name="de_dust2")
    )

    importer.skip(candidate)

    assert importer.ledger.knows(DemoFile(source)) is True
    assert not staged.exists()


def test_a_file_that_changed_size_counts_as_new(tmp_path: Path):
    source = tmp_path / "raw.dem"
    source.write_bytes(PAYLOAD)
    ledger = ImportLedger(tmp_path / "work")
    ledger.remember(DemoFile(source), "dust2.dem", "de_dust2", 1.0)

    source.write_bytes(PAYLOAD + b"more")

    assert ledger.knows(DemoFile(source)) is False


def test_a_broken_ledger_is_ignored(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "imported_demos.json").write_text("{not json", encoding="utf-8")

    assert ImportLedger(work).knows(DemoFile(tmp_path / "a.dem")) is False


def test_a_ledger_from_another_version_is_ignored(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "imported_demos.json").write_text(
        json.dumps({"version": 99, "demos": []}), encoding="utf-8"
    )

    assert ImportLedger(work)._records == {}


def test_the_demo_folder_is_never_searched(tmp_path: Path):
    locator = DemoSourceLocator(None)
    directories = [str(item).lower() for item in locator.directories()]

    assert not any(item.endswith("demos") for item in directories)


def test_a_faceit_demo_is_recognised_by_its_server():
    assert DemoSummary("de_dust2", "FACEIT.com register to play here").is_faceit is True
    assert DemoSummary("de_dust2", "Valve Counter-Strike").is_faceit is False


def test_the_demoget_flag_is_understood():
    from highlighter.cli import CommandLine

    assert CommandLine.parse(["-demoget"]).demo_get is True
    assert CommandLine.parse(["--demoget"]).demo_get is True
    assert CommandLine.parse(["match.dem"]).demo_get is False
