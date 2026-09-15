from __future__ import annotations

import bz2
import gzip
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..infrastructure.errors import HighlighterError
from ..infrastructure.logging import get_logger

DEMO_SUFFIX = ".dem"
ZSTD_SUFFIX = ".zst"
GZIP_SUFFIX = ".gz"
BZIP2_SUFFIX = ".bz2"
ARCHIVE_SUFFIXES = (ZSTD_SUFFIX, GZIP_SUFFIX, BZIP2_SUFFIX)
CHUNK_SIZE = 1 << 20


class ArchiveError(HighlighterError):
    pass


@dataclass(frozen=True, slots=True)
class DemoFile:
    path: Path

    @property
    def is_archive(self) -> bool:
        return self.path.suffix.lower() in ARCHIVE_SUFFIXES

    @property
    def demo_name(self) -> str:
        name = self.path.name
        for suffix in ARCHIVE_SUFFIXES:
            if name.lower().endswith(suffix):
                name = name[: -len(suffix)]
                break
        return Path(name).stem

    @property
    def size_bytes(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    @property
    def modified_at(self) -> float:
        try:
            return self.path.stat().st_mtime
        except OSError:
            return 0.0


class DemoExtractor:
    def __init__(self) -> None:
        self._logger = get_logger("importing.archive")

    def extract(self, source: DemoFile, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not source.is_archive:
            shutil.copy2(source.path, destination)
            return destination

        opener = self._opener(source.path)
        try:
            opener(source.path, destination)
        except ArchiveError:
            raise
        except BaseException as error:
            destination.unlink(missing_ok=True)
            raise ArchiveError(
                f"{source.path.name} could not be unpacked: {error}"
            ) from error

        self._logger.debug("Unpacked %s to %s", source.path.name, destination)
        return destination

    def _opener(self, path: Path) -> Callable[[Path, Path], None]:
        suffix = path.suffix.lower()
        if suffix == ZSTD_SUFFIX:
            return self._unpack_zstd
        if suffix == GZIP_SUFFIX:
            return self._unpack_gzip
        if suffix == BZIP2_SUFFIX:
            return self._unpack_bzip2
        raise ArchiveError(f"{path.name} is not a demo archive this build can open")

    @staticmethod
    def _unpack_zstd(source: Path, destination: Path) -> None:
        import pyarrow

        with pyarrow.CompressedInputStream(
            pyarrow.OSFile(str(source), "rb"), "zstd"
        ) as stream, open(destination, "wb") as sink:
            while True:
                chunk = stream.read(CHUNK_SIZE)
                if not chunk:
                    break
                sink.write(chunk)

    @staticmethod
    def _unpack_gzip(source: Path, destination: Path) -> None:
        with gzip.open(source, "rb") as stream, open(destination, "wb") as sink:
            shutil.copyfileobj(stream, sink, CHUNK_SIZE)

    @staticmethod
    def _unpack_bzip2(source: Path, destination: Path) -> None:
        with bz2.open(source, "rb") as stream, open(destination, "wb") as sink:
            shutil.copyfileobj(stream, sink, CHUNK_SIZE)
