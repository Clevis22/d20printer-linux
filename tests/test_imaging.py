import tempfile
import unittest
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    Image = None

from d20printer.imaging import pack_monochrome, prepare_image, render_text


@unittest.skipIf(Image is None, "Pillow is not installed")
class ImagingTests(unittest.TestCase):
    def test_pack_monochrome_is_msb_first(self):
        image = Image.new("1", (8, 1), 1)
        pixels = image.load()
        pixels[0, 0] = 0
        pixels[2, 0] = 0
        pixels[7, 0] = 0
        self.assertEqual(pack_monochrome(image).data, bytes((0b10100001,)))

    def test_prepare_image_scales_to_384_dots(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.png"
            Image.new("L", (192, 50), 255).save(path)
            raster = prepare_image(path)
        self.assertEqual((raster.width, raster.height), (384, 100))
        self.assertEqual(len(raster.data), 48 * 100)

    def test_text_raster_has_black_pixels(self):
        raster = render_text("Hello from Linux", font_size=24)
        self.assertEqual(raster.width, 384)
        self.assertGreater(raster.height, 24)
        self.assertTrue(any(raster.data))


if __name__ == "__main__":
    unittest.main()
