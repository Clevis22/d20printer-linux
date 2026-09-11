"""Wire-level commands and reply decoding for the Nada D20 protocol."""

from __future__ import annotations

from dataclasses import dataclass


PRINT_WIDTH_DOTS = 384
BYTES_PER_ROW = PRINT_WIDTH_DOTS // 8
RFCOMM_CHANNEL = 1
SPP_UUID = "00001101-0000-1000-8000-00805F9B34FB"

PRINT_SUCCESS_SELECTOR = 0x0F
PRINT_SUCCESS_VALUE = 0x0C


def _vendor_query(selector: int) -> bytes:
    return bytes((0x1F, 0x11, 0x05, selector))


QUERY_FIRMWARE = _vendor_query(0x07)
QUERY_SERIAL = _vendor_query(0x09)
QUERY_BATTERY = _vendor_query(0x08)
QUERY_COVER = _vendor_query(0x12)
QUERY_PAPER = _vendor_query(0x11)
QUERY_SHUTDOWN = _vendor_query(0x0E)
QUERY_TEMPERATURE = _vendor_query(0x13)
QUERY_BUSY = _vendor_query(0x2F)


@dataclass(frozen=True)
class Raster:
    """A top-to-bottom, MSB-first, 1-bit image."""

    width: int
    height: int
    data: bytes

    def __post_init__(self) -> None:
        if self.width <= 0 or self.width % 8:
            raise ValueError("raster width must be a positive multiple of 8")
        if not 0 < self.height <= 0xFFFF:
            raise ValueError("raster height must be between 1 and 65535")
        expected = (self.width // 8) * self.height
        if len(self.data) != expected:
            raise ValueError(f"raster contains {len(self.data)} bytes; expected {expected}")

    @property
    def bytes_per_row(self) -> int:
        return self.width // 8

    def rows(self, start: int, count: int) -> "Raster":
        if start < 0 or count <= 0 or start + count > self.height:
            raise ValueError("invalid raster row range")
        first = start * self.bytes_per_row
        last = (start + count) * self.bytes_per_row
        return Raster(self.width, count, self.data[first:last])


@dataclass(frozen=True)
class Reply:
    marker: int
    selector: int
    payload: bytes
    raw: bytes


def set_density(level: int) -> bytes:
    if not 1 <= level <= 4:
        raise ValueError("density must be between 1 and 4")
    return bytes((0x1F, 0x11, 0x05, 0x02, level))


def set_raw_mode() -> bytes:
    return bytes.fromhex("1f 11 05 35 00")


def set_paper_type(value: int = 0) -> bytes:
    if not 0 <= value <= 0xFF:
        raise ValueError("paper type must fit in one byte")
    return bytes((0x1B, 0x4E, 0x06, 0x0A, value))


def raster_command(raster: Raster) -> bytes:
    return (
        bytes.fromhex("1d 76 30 00")
        + raster.bytes_per_row.to_bytes(2, "little")
        + raster.height.to_bytes(2, "little")
        + raster.data
    )


def blank_raster(height: int) -> Raster:
    return Raster(PRINT_WIDTH_DOTS, height, bytes(BYTES_PER_ROW * height))


def split_raster(raster: Raster, max_rows: int = 255) -> list[Raster]:
    if max_rows <= 0:
        raise ValueError("max_rows must be positive")
    result: list[Raster] = []
    for start in range(0, raster.height, max_rows):
        result.append(raster.rows(start, min(max_rows, raster.height - start)))
    return result


def parse_replies(data: bytes) -> list[Reply]:
    """Parse complete `1A/1C selector payload 0D` frames from captured bytes."""

    replies: list[Reply] = []
    offset = 0
    while offset < len(data):
        while offset < len(data) and data[offset] not in (0x1A, 0x1C):
            offset += 1
        if offset >= len(data):
            break
        end = data.find(b"\x0d", offset + 2)
        if end < 0:
            break
        raw = data[offset : end + 1]
        if len(raw) >= 3:
            replies.append(Reply(raw[0], raw[1], raw[2:-1], raw))
        offset = end + 1
    return replies


def print_succeeded(replies: list[Reply]) -> bool:
    return any(
        reply.selector == PRINT_SUCCESS_SELECTOR
        and reply.payload[:1] == bytes((PRINT_SUCCESS_VALUE,))
        for reply in replies
    )
