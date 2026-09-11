"""High-level D20 printer operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .protocol import (
    QUERY_BATTERY,
    QUERY_BUSY,
    QUERY_COVER,
    QUERY_FIRMWARE,
    QUERY_PAPER,
    QUERY_SERIAL,
    QUERY_SHUTDOWN,
    QUERY_TEMPERATURE,
    Raster,
    Reply,
    blank_raster,
    parse_replies,
    print_succeeded,
    raster_command,
    set_density,
    set_paper_type,
    set_raw_mode,
    split_raster,
)
from .transport import RFCOMMTransport


class Transport(Protocol):
    def connect(self) -> None: ...
    def close(self) -> None: ...
    def send(self, data: bytes) -> None: ...
    def exchange(self, data: bytes, timeout: float) -> bytes: ...


@dataclass(frozen=True)
class PrinterStatus:
    firmware: str | None = None
    serial: str | None = None
    battery_percent: int | None = None
    cover_open: bool | None = None
    paper_present: bool | None = None
    shutdown_time: int | None = None
    temperature_normal: bool | None = None
    busy: bool | None = None


def _single_reply(transport: Transport, command: bytes) -> Reply | None:
    replies = parse_replies(transport.exchange(command, timeout=1.5))
    return replies[0] if replies else None


class D20Printer:
    def __init__(self, address: str, transport: Transport | None = None) -> None:
        self.address = address
        self.transport = transport or RFCOMMTransport(address)

    def connect(self) -> None:
        self.transport.connect()

    def close(self) -> None:
        self.transport.close()

    def __enter__(self) -> "D20Printer":
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def status(self) -> PrinterStatus:
        replies = {
            name: _single_reply(self.transport, command)
            for name, command in (
                ("firmware", QUERY_FIRMWARE),
                ("serial", QUERY_SERIAL),
                ("battery", QUERY_BATTERY),
                ("cover", QUERY_COVER),
                ("paper", QUERY_PAPER),
                ("shutdown", QUERY_SHUTDOWN),
                ("temperature", QUERY_TEMPERATURE),
                ("busy", QUERY_BUSY),
            )
        }

        def payload(name: str) -> bytes:
            reply = replies[name]
            return reply.payload if reply is not None else b""

        firmware_bytes = payload("firmware")
        firmware = (
            ".".join(str(value) for value in firmware_bytes[:3])
            if len(firmware_bytes) >= 3
            else None
        )
        serial_bytes = payload("serial")
        try:
            serial = serial_bytes[:15].decode("ascii") if serial_bytes else None
        except UnicodeDecodeError:
            serial = serial_bytes[:15].hex()

        battery = payload("battery")
        cover = payload("cover")
        paper = payload("paper")
        shutdown = payload("shutdown")
        temperature = payload("temperature")
        busy_reply = replies["busy"]

        return PrinterStatus(
            firmware=firmware,
            serial=serial,
            battery_percent=battery[0] if battery else None,
            cover_open=(cover[0] == 0x99) if cover else None,
            paper_present=(paper[0] != 0x88) if paper else None,
            shutdown_time=shutdown[0] if shutdown else None,
            temperature_normal=(temperature[0] == 0xA8) if temperature else None,
            busy=(busy_reply.selector != 0x38) if busy_reply else None,
        )

    def preflight(self) -> PrinterStatus:
        """Check conditions that would make starting a print unsafe or futile."""
        status = self.status()
        problems: list[str] = []
        if status.cover_open is True:
            problems.append("cover is open")
        if status.paper_present is False:
            problems.append("paper is absent")
        if status.temperature_normal is False:
            problems.append("print head is overheated")
        if status.busy is True:
            problems.append("printer is busy")
        if problems:
            raise RuntimeError("; ".join(problems))
        return status

    def configure(self, density: int = 2, paper_type: int = 0) -> None:
        self.transport.send(set_paper_type(paper_type))
        self.transport.send(set_density(density))
        self.transport.send(set_raw_mode())

    def _print_block(self, raster: Raster, timeout: float) -> None:
        raw_reply = self.transport.exchange(raster_command(raster), timeout=timeout)
        replies = parse_replies(raw_reply)
        if not print_succeeded(replies):
            rendered = raw_reply.hex(" ") or "no response"
            raise RuntimeError(f"printer did not confirm completion: {rendered}")

    def print_raster(
        self,
        raster: Raster,
        *,
        density: int = 2,
        paper_type: int = 0,
        feed_rows: int = 64,
        block_rows: int = 255,
        timeout: float = 30.0,
    ) -> None:
        self.configure(density=density, paper_type=paper_type)
        for block in split_raster(raster, max_rows=block_rows):
            self._print_block(block, timeout)
        if feed_rows:
            self._print_block(blank_raster(feed_rows), timeout)
