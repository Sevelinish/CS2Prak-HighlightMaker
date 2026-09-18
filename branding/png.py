from __future__ import annotations

import struct
import zlib

from .raster import Bitmap

SIGNATURE = b"\x89PNG\r\n\x1a\n"
BIT_DEPTH = 8
COLOR_TYPE_RGBA = 6
NO_FILTER = b"\x00"


class PngWriter:
    @classmethod
    def encode(cls, bitmap: Bitmap) -> bytes:
        return b"".join(
            [
                SIGNATURE,
                cls._chunk(b"IHDR", cls._header(bitmap)),
                cls._chunk(b"IDAT", zlib.compress(cls._raw(bitmap), 9)),
                cls._chunk(b"IEND", b""),
            ]
        )

    @staticmethod
    def _header(bitmap: Bitmap) -> bytes:
        return struct.pack(
            ">IIBBBBB", bitmap.width, bitmap.height, BIT_DEPTH, COLOR_TYPE_RGBA, 0, 0, 0
        )

    @staticmethod
    def _raw(bitmap: Bitmap) -> bytes:
        return b"".join(NO_FILTER + row for row in bitmap.rows())

    @staticmethod
    def _chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))
