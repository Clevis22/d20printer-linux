import unittest
from unittest.mock import patch

from d20printer.printer import D20Printer, PrinterStatus
from d20printer.protocol import Raster


class FakeTransport:
    def __init__(self):
        self.sent = []
        self.connected = False

    def connect(self):
        self.connected = True

    def close(self):
        self.connected = False

    def send(self, data):
        self.sent.append(data)

    def exchange(self, data, timeout):
        self.sent.append(data)
        return bytes.fromhex("1c 0f 0c 0d")


class PrinterTests(unittest.TestCase):
    def test_print_sends_config_blocks_and_feed(self):
        transport = FakeTransport()
        printer = D20Printer("00:00:00:00:00:00", transport=transport)
        printer.print_raster(Raster(384, 300, bytes(48 * 300)), density=1)
        self.assertEqual(transport.sent[0], bytes.fromhex("1b 4e 06 0a 00"))
        self.assertEqual(transport.sent[1], bytes.fromhex("1f 11 05 02 01"))
        self.assertEqual(transport.sent[2], bytes.fromhex("1f 11 05 35 00"))
        raster_heights = [int.from_bytes(item[6:8], "little") for item in transport.sent[3:]]
        self.assertEqual(raster_heights, [255, 45, 64])

    def test_preflight_accepts_ready_printer(self):
        printer = D20Printer("00:00:00:00:00:00", transport=FakeTransport())
        ready = PrinterStatus(
            cover_open=False,
            paper_present=True,
            temperature_normal=True,
            busy=False,
        )
        with patch.object(printer, "status", return_value=ready):
            self.assertEqual(printer.preflight(), ready)

    def test_preflight_reports_all_known_problems(self):
        printer = D20Printer("00:00:00:00:00:00", transport=FakeTransport())
        blocked = PrinterStatus(
            cover_open=True,
            paper_present=False,
            temperature_normal=False,
            busy=True,
        )
        with patch.object(printer, "status", return_value=blocked):
            with self.assertRaisesRegex(RuntimeError, "cover is open.*paper is absent.*overheated.*busy"):
                printer.preflight()


if __name__ == "__main__":
    unittest.main()
