from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from .dib import DibWriter
from .png import PngWriter
from .raster import Bitmap, Rasterizer
from .svg import Drawing, SvgReader

ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)
COMPRESSED_FROM = 128
MASTER_SIZE = 512
DIRECTORY_HEADER = 6
ENTRY_SIZE = 16
ICON_TYPE = 1
PLANES = 1
BITS_PER_PIXEL = 32
LARGEST_DECLARED = 256


@dataclass(frozen=True, slots=True)
class IconImage:
    size: int
    payload: bytes


class IconWriter:
    def __init__(self, sizes: tuple[int, ...] = ICON_SIZES) -> None:
        self._sizes = tuple(sorted(set(sizes)))

    def encode(self, master: Bitmap) -> bytes:
        images = [self._image(master, size) for size in self._sizes]
        offset = DIRECTORY_HEADER + ENTRY_SIZE * len(images)

        directory = bytearray(struct.pack("<HHH", 0, ICON_TYPE, len(images)))
        body = bytearray()
        for image in images:
            directory += self._entry(image, offset + len(body))
            body += image.payload
        return bytes(directory + body)

    @staticmethod
    def _image(master: Bitmap, size: int) -> IconImage:
        scaled = master.resized(size)
        writer = PngWriter if size >= COMPRESSED_FROM else DibWriter
        return IconImage(size=size, payload=writer.encode(scaled))

    @staticmethod
    def _entry(image: IconImage, offset: int) -> bytes:
        declared = 0 if image.size >= LARGEST_DECLARED else image.size
        return struct.pack(
            "<BBBBHHII",
            declared,
            declared,
            0,
            0,
            PLANES,
            BITS_PER_PIXEL,
            len(image.payload),
            offset,
        )


class IconBuilder:
    def __init__(
        self,
        reader: SvgReader | None = None,
        rasterizer: Rasterizer | None = None,
        writer: IconWriter | None = None,
    ) -> None:
        self._reader = reader or SvgReader()
        self._rasterizer = rasterizer or Rasterizer()
        self._writer = writer or IconWriter()

    def build(self, logo: Path, destination: Path) -> Path:
        drawing = self._reader.read(logo)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self._writer.encode(self.master(drawing)))
        return destination

    def master(self, drawing: Drawing, size: int = MASTER_SIZE) -> Bitmap:
        return self._rasterizer.render(drawing, size)
