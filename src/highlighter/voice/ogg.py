from __future__ import annotations

import struct
from typing import Sequence

from .packets import FRAME_SAMPLES, SAMPLE_RATE

CAPTURE_PATTERN = b"OggS"
STREAM_VERSION = 0
FLAG_CONTINUED = 0x01
FLAG_FIRST = 0x02
FLAG_LAST = 0x04
CHECKSUM_OFFSET = 22
CHECKSUM_END = 26
MAXIMUM_SEGMENT = 255
PACKETS_PER_PAGE = 20
HEAD_MAGIC = b"OpusHead"
TAGS_MAGIC = b"OpusTags"
OPUS_VERSION = 1
CHANNELS = 1
PRE_SKIP = 312
OUTPUT_GAIN = 0
MAPPING_FAMILY = 0
VENDOR = b"HighlighterCS2"
POLYNOMIAL = 0x04C11DB7
WORD_MASK = 0xFFFFFFFF
HIGH_BIT = 0x80000000


def _table() -> tuple[int, ...]:
    entries = []
    for index in range(256):
        value = index << 24
        for _ in range(8):
            if value & HIGH_BIT:
                value = ((value << 1) ^ POLYNOMIAL) & WORD_MASK
            else:
                value = (value << 1) & WORD_MASK
        entries.append(value)
    return tuple(entries)


CRC_TABLE = _table()


class OggChecksum:
    @staticmethod
    def of(data: bytes) -> int:
        value = 0
        for byte in data:
            value = ((value << 8) & WORD_MASK) ^ CRC_TABLE[((value >> 24) & 0xFF) ^ byte]
        return value


class OggOpusWriter:
    def __init__(self, serial: int = 1, packets_per_page: int = PACKETS_PER_PAGE) -> None:
        self._serial = serial & WORD_MASK
        self._packets_per_page = max(1, packets_per_page)

    def render(self, payloads: Sequence[bytes]) -> bytes:
        stream = bytearray()
        stream += self._page(0, 0, [self._head()], FLAG_FIRST)
        stream += self._page(1, 0, [self._tags()], 0)

        sequence = 2
        granule = 0
        for index in range(0, len(payloads), self._packets_per_page):
            chunk = list(payloads[index : index + self._packets_per_page])
            granule += FRAME_SAMPLES * len(chunk)
            last = index + self._packets_per_page >= len(payloads)
            stream += self._page(sequence, granule, chunk, FLAG_LAST if last else 0)
            sequence += 1
        return bytes(stream)

    def _page(
        self, sequence: int, granule: int, packets: Sequence[bytes], flags: int
    ) -> bytes:
        segments = bytearray()
        body = bytearray()
        for packet in packets:
            remaining = len(packet)
            while remaining >= MAXIMUM_SEGMENT:
                segments.append(MAXIMUM_SEGMENT)
                remaining -= MAXIMUM_SEGMENT
            segments.append(remaining)
            body += packet

        header = bytearray(CAPTURE_PATTERN)
        header += bytes([STREAM_VERSION, flags])
        header += struct.pack("<q", granule)
        header += struct.pack("<II", self._serial, sequence)
        header += bytes(4)
        header += bytes([len(segments)])
        header += segments

        page = bytes(header) + bytes(body)
        checksum = struct.pack("<I", OggChecksum.of(page))
        return page[:CHECKSUM_OFFSET] + checksum + page[CHECKSUM_END:]

    @staticmethod
    def _head() -> bytes:
        return HEAD_MAGIC + bytes([OPUS_VERSION, CHANNELS]) + struct.pack(
            "<HIhB", PRE_SKIP, SAMPLE_RATE, OUTPUT_GAIN, MAPPING_FAMILY
        )

    @staticmethod
    def _tags() -> bytes:
        return TAGS_MAGIC + struct.pack("<I", len(VENDOR)) + VENDOR + struct.pack("<I", 0)
