from __future__ import annotations

import struct

from .raster import Bitmap

HEADER_SIZE = 40
PLANES = 1
BITS_PER_PIXEL = 32
MASK_ALIGNMENT = 32
BITS_PER_BYTE = 8


class DibWriter:
    @classmethod
    def encode(cls, bitmap: Bitmap) -> bytes:
        return cls._header(bitmap) + cls._colors(bitmap) + cls._mask(bitmap)

    @staticmethod
    def _header(bitmap: Bitmap) -> bytes:
        return struct.pack(
            "<IiiHHIIiiII",
            HEADER_SIZE,
            bitmap.width,
            bitmap.height * 2,
            PLANES,
            BITS_PER_PIXEL,
            0,
            0,
            0,
            0,
            0,
            0,
        )

    @staticmethod
    def _colors(bitmap: Bitmap) -> bytes:
        rows = bytearray()
        for y in range(bitmap.height - 1, -1, -1):
            for x in range(bitmap.width):
                red, green, blue, alpha = bitmap.pixel(x, y)
                rows += bytes((blue, green, red, alpha))
        return bytes(rows)

    @staticmethod
    def _mask(bitmap: Bitmap) -> bytes:
        stride = ((bitmap.width + MASK_ALIGNMENT - 1) // MASK_ALIGNMENT) * (
            MASK_ALIGNMENT // BITS_PER_BYTE
        )
        return bytes(stride * bitmap.height)
