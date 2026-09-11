#!/usr/bin/env python3
"""Issue read-only Nada D20 status queries over Bluetooth Classic RFCOMM."""

from __future__ import annotations

import argparse
import socket
import time


QUERIES = (
    ("firmware", bytes.fromhex("1f 11 05 07")),
    ("serial", bytes.fromhex("1f 11 05 09")),
    ("battery", bytes.fromhex("1f 11 05 08")),
    ("cover", bytes.fromhex("1f 11 05 12")),
    ("paper", bytes.fromhex("1f 11 05 11")),
    ("shutdown", bytes.fromhex("1f 11 05 0e")),
    ("temperature", bytes.fromhex("1f 11 05 13")),
    ("busy", bytes.fromhex("1f 11 05 2f")),
)


def receive_available(sock: socket.socket, timeout: float) -> bytes:
    deadline = time.monotonic() + timeout
    chunks: list[bytes] = []
    while time.monotonic() < deadline:
        try:
            chunk = sock.recv(1024)
        except TimeoutError:
            continue
        if not chunk:
            break
        chunks.append(chunk)
        # Replies are short; allow a brief interval for a fragmented tail.
        deadline = min(deadline, time.monotonic() + 0.15)
    return b"".join(chunks)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("address", help="Bluetooth MAC address, e.g. AA:BB:CC:DD:EE:FF")
    parser.add_argument("--channel", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=1.5)
    args = parser.parse_args()

    with socket.socket(
        socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM
    ) as sock:
        sock.settimeout(10.0)
        sock.connect((args.address, args.channel))
        sock.settimeout(0.10)
        print(f"connected {args.address} channel {args.channel}")
        for name, command in QUERIES:
            sock.sendall(command)
            response = receive_available(sock, args.timeout)
            print(f"{name:11s} tx={command.hex(' ')} rx={response.hex(' ') or '<none>'}")


if __name__ == "__main__":
    main()
