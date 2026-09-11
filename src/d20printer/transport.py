"""Linux Bluetooth Classic RFCOMM transport."""

from __future__ import annotations

import errno
import socket
import time
from types import TracebackType

from .protocol import RFCOMM_CHANNEL


class RFCOMMTransport:
    def __init__(
        self,
        address: str,
        channel: int = RFCOMM_CHANNEL,
        connect_timeout: float = 10.0,
        busy_retry_timeout: float = 5.0,
    ) -> None:
        self.address = address
        self.channel = channel
        self.connect_timeout = connect_timeout
        self.busy_retry_timeout = busy_retry_timeout
        self._socket: socket.socket | None = None

    def connect(self) -> None:
        if self._socket is not None:
            return
        required = ("AF_BLUETOOTH", "BTPROTO_RFCOMM")
        if any(not hasattr(socket, name) for name in required):
            raise RuntimeError("native Bluetooth RFCOMM sockets require Linux")
        retry_deadline = time.monotonic() + self.busy_retry_timeout
        while True:
            sock = socket.socket(
                socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM
            )
            try:
                sock.settimeout(self.connect_timeout)
                sock.connect((self.address, self.channel))
                sock.settimeout(0.10)
            except OSError as error:
                sock.close()
                if error.errno == errno.EBUSY and time.monotonic() < retry_deadline:
                    time.sleep(0.25)
                    continue
                raise
            except Exception:
                sock.close()
                raise
            self._socket = sock
            return

    def close(self) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def send(self, data: bytes) -> None:
        if self._socket is None:
            raise RuntimeError("transport is not connected")
        self._socket.sendall(data)

    def receive_until_quiet(self, timeout: float, quiet: float = 0.15) -> bytes:
        if self._socket is None:
            raise RuntimeError("transport is not connected")
        deadline = time.monotonic() + timeout
        chunks: list[bytes] = []
        last_data: float | None = None
        while time.monotonic() < deadline:
            if last_data is not None and time.monotonic() - last_data >= quiet:
                break
            try:
                chunk = self._socket.recv(1024)
            except TimeoutError:
                continue
            if not chunk:
                break
            chunks.append(chunk)
            last_data = time.monotonic()
        return b"".join(chunks)

    def exchange(self, data: bytes, timeout: float) -> bytes:
        self.send(data)
        return self.receive_until_quiet(timeout)

    def __enter__(self) -> "RFCOMMTransport":
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
