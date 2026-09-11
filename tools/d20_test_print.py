#!/usr/bin/env python3
"""Print a small, low-density diagnostic pattern on a Nada/Jiuyin D20."""

from __future__ import annotations

import argparse
import socket
import time


WIDTH = 384
HEIGHT = 96
BYTES_PER_ROW = WIDTH // 8


def set_pixel(raster: bytearray, x: int, y: int) -> None:
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        raster[y * BYTES_PER_ROW + x // 8] |= 1 << (7 - (x % 8))


def make_pattern() -> bytes:
    raster = bytearray(BYTES_PER_ROW * HEIGHT)

    # Edge registration marks and an asymmetric diagonal establish orientation.
    for y in range(HEIGHT):
        set_pixel(raster, 0, y)
        set_pixel(raster, WIDTH - 1, y)
        set_pixel(raster, 4 * y, y)

    # Sparse horizontal rulers at the top, middle, and bottom.
    for y, spacing in ((0, 8), (HEIGHT // 2, 16), (HEIGHT - 1, 8)):
        for x in range(0, WIDTH, spacing):
            set_pixel(raster, x, y)

    # Three differently placed 7x7 corner boxes make rotations obvious.
    for origin_x, origin_y in ((8, 8), (32, 24), (WIDTH - 16, 72)):
        for offset in range(7):
            set_pixel(raster, origin_x + offset, origin_y)
            set_pixel(raster, origin_x + offset, origin_y + 6)
            set_pixel(raster, origin_x, origin_y + offset)
            set_pixel(raster, origin_x + 6, origin_y + offset)

    return bytes(raster)


def raster_command(width_bytes: int, height: int, payload: bytes) -> bytes:
    expected = width_bytes * height
    if len(payload) != expected:
        raise ValueError(f"payload is {len(payload)} bytes; expected {expected}")
    return (
        bytes.fromhex("1d 76 30 00")
        + width_bytes.to_bytes(2, "little")
        + height.to_bytes(2, "little")
        + payload
    )


def receive_until_quiet(sock: socket.socket, seconds: float) -> bytes:
    deadline = time.monotonic() + seconds
    chunks: list[bytes] = []
    while time.monotonic() < deadline:
        try:
            chunk = sock.recv(1024)
        except TimeoutError:
            continue
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def send(sock: socket.socket, label: str, data: bytes, wait: float = 0.25) -> None:
    sock.sendall(data)
    response = receive_until_quiet(sock, wait)
    print(
        f"{label:14s} tx={len(data):5d} bytes "
        f"rx={response.hex(' ') or '<none>'}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("address", help="D20 Bluetooth MAC address")
    parser.add_argument("--channel", type=int, default=1)
    args = parser.parse_args()

    pattern = make_pattern()
    print_job = raster_command(BYTES_PER_ROW, HEIGHT, pattern)
    feed_job = raster_command(BYTES_PER_ROW, 64, bytes(BYTES_PER_ROW * 64))

    with socket.socket(
        socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM
    ) as sock:
        sock.settimeout(10.0)
        sock.connect((args.address, args.channel))
        sock.settimeout(0.10)
        print(f"connected {args.address} channel {args.channel}")

        # Match Nada Print's raw-data path, using its lowest supported density.
        send(sock, "paper type", bytes.fromhex("1b 4e 06 0a 00"))
        send(sock, "density 1", bytes.fromhex("1f 11 05 02 01"))
        send(sock, "raw mode", bytes.fromhex("1f 11 05 35 00"))
        send(sock, "test raster", print_job, wait=2.0)
        send(sock, "blank feed", feed_job, wait=3.0)

        # Confirm the printer returned to an idle, healthy state.
        send(sock, "paper query", bytes.fromhex("1f 11 05 11"), wait=0.5)
        send(sock, "temp query", bytes.fromhex("1f 11 05 13"), wait=0.5)
        send(sock, "busy query", bytes.fromhex("1f 11 05 2f"), wait=0.5)


if __name__ == "__main__":
    main()
