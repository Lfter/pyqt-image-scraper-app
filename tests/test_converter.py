import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.converter import ImageConverter


class ImageConverterTests(unittest.TestCase):
    def test_convert_bmp_to_jpeg_copy(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "sample.bmp"
            Image.new("RGB", (4, 4), color=(255, 0, 0)).save(source_path, "BMP")

            converter = ImageConverter()
            converted_path = converter.convert_file(str(source_path))

            self.assertEqual(Path(converted_path).suffix.lower(), ".jpg")
            self.assertTrue(Path(converted_path).exists())
            self.assertTrue(source_path.exists())
            self.assertIn("_compatible", Path(converted_path).stem)

    def test_convert_transparent_tiff_to_png_copy(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "transparent.tiff"
            Image.new("RGBA", (4, 4), color=(0, 0, 255, 80)).save(source_path, "TIFF")

            converter = ImageConverter()
            converted_path = converter.convert_file(str(source_path))

            self.assertEqual(Path(converted_path).suffix.lower(), ".png")
            self.assertTrue(Path(converted_path).exists())
            self.assertTrue(source_path.exists())

    def test_skip_non_convertible_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "plain.png"
            source_path.write_bytes(b"png")

            converter = ImageConverter()
            self.assertIsNone(converter.convert_file(str(source_path)))


if __name__ == "__main__":
    unittest.main()
