import unittest

from d20printer.protocol import (
    Raster,
    parse_replies,
    print_succeeded,
    raster_command,
    set_density,
    split_raster,
)


class ProtocolTests(unittest.TestCase):
    def test_density_range_and_bytes(self):
        self.assertEqual(set_density(1), bytes.fromhex("1f 11 05 02 01"))
        self.assertEqual(set_density(4), bytes.fromhex("1f 11 05 02 04"))
        with self.assertRaises(ValueError):
            set_density(0)

    def test_raster_command_header(self):
        raster = Raster(384, 2, bytes(96))
        command = raster_command(raster)
        self.assertEqual(command[:8], bytes.fromhex("1d 76 30 00 30 00 02 00"))
        self.assertEqual(len(command), 104)

    def test_raster_validation(self):
        with self.assertRaises(ValueError):
            Raster(383, 1, b"")
        with self.assertRaises(ValueError):
            Raster(384, 2, bytes(48))

    def test_split_raster_preserves_data(self):
        source = bytes(index % 256 for index in range(48 * 600))
        blocks = split_raster(Raster(384, 600, source), max_rows=255)
        self.assertEqual([block.height for block in blocks], [255, 255, 90])
        self.assertEqual(b"".join(block.data for block in blocks), source)

    def test_reply_parser(self):
        raw = bytes.fromhex("1c 07 01 00 00 0d 1c 04 46 0d")
        replies = parse_replies(raw)
        self.assertEqual(len(replies), 2)
        self.assertEqual(replies[0].selector, 0x07)
        self.assertEqual(replies[0].payload, bytes((1, 0, 0)))
        self.assertEqual(replies[1].payload, bytes((70,)))

    def test_print_success(self):
        replies = parse_replies(bytes.fromhex("1c 0f 0c 0d"))
        self.assertTrue(print_succeeded(replies))
        self.assertFalse(print_succeeded(parse_replies(bytes.fromhex("1c 0f 00 0d"))))


if __name__ == "__main__":
    unittest.main()
