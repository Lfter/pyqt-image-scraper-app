import os
import sys
import tempfile
import unittest
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.downloader import ImageDownloader
from utils import helpers


class FakeResponse:
    def __init__(self, headers=None, chunks=None, error=None, url=None):
        self.headers = headers or {}
        self._chunks = chunks or []
        self._error = error
        self.url = url

    def raise_for_status(self):
        if self._error:
            raise self._error

    def iter_content(self, chunk_size=8192):
        del chunk_size
        for chunk in self._chunks:
            yield chunk


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []
        self.headers = {}

    def get(self, url, timeout=20, stream=False, headers=None):
        self.calls.append(
            {
                "url": url,
                "timeout": timeout,
                "stream": stream,
                "headers": headers or {},
            }
        )
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        return response


class ImageDownloaderTests(unittest.TestCase):
    def test_download_images_saves_files_and_updates_progress(self):
        image_url = "https://img.example.com/photo"
        session = FakeSession(
            {
                image_url: FakeResponse(
                    headers={"Content-Type": "image/png"},
                    chunks=[b"first", b"second"],
                )
            }
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = ImageDownloader(session, "https://example.com/page", temp_dir)
            progress_updates = []
            status_updates = []

            summary = downloader.download_images(
                [image_url, image_url],
                progress_callback=progress_updates.append,
                status_callback=status_updates.append,
            )

            self.assertEqual(summary.success_count, 2)
            self.assertEqual(summary.converted_count, 0)
            self.assertEqual(progress_updates, [50, 100])
            self.assertEqual(status_updates, ["正在下载：1/2", "正在下载：2/2"])
            self.assertEqual(session.calls[0]["headers"]["Referer"], "https://example.com/page")

            expected_name = downloader.build_filename(image_url, ".png")
            root, ext = os.path.splitext(expected_name)
            expected_files = sorted([expected_name, f"{root}_1{ext}"])
            saved_files = sorted(path.name for path in (Path(temp_dir) / "PNG").iterdir())
            self.assertEqual(saved_files, expected_files)

    def test_download_images_records_failures_without_losing_successes(self):
        good_url = "https://img.example.com/photo.jpg"
        bad_url = "https://img.example.com/missing.jpg"
        session = FakeSession(
            {
                good_url: FakeResponse(
                    headers={"Content-Type": "image/jpeg"},
                    chunks=[b"ok"],
                ),
                bad_url: requests.HTTPError("404"),
            }
        )

        original_log_dir = helpers.LOG_DIR

        with tempfile.TemporaryDirectory() as temp_dir:
            helpers.LOG_DIR = Path(temp_dir) / "logs"
            try:
                downloader = ImageDownloader(session, "https://example.com/page", temp_dir)
                summary = downloader.download_images([good_url, bad_url])
            finally:
                helpers.LOG_DIR = original_log_dir

            self.assertEqual(summary.success_count, 1)
            failure_log = Path(temp_dir) / "logs" / "failed_images.txt"
            self.assertTrue(failure_log.exists())
            self.assertIn(bad_url, failure_log.read_text(encoding="utf-8"))
            self.assertTrue((Path(temp_dir) / "JPEG" / "photo.jpg").exists())

    def test_download_images_raises_when_all_downloads_fail(self):
        bad_url = "https://img.example.com/missing.png"
        session = FakeSession({bad_url: requests.ConnectionError("network down")})

        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = ImageDownloader(session, "https://example.com/page", temp_dir)
            with self.assertRaisesRegex(ValueError, "全部下载失败"):
                downloader.download_images([bad_url])

    def test_download_images_generates_compatible_copy_when_enabled(self):
        image_url = "https://img.example.com/source.bmp"
        session = FakeSession(
            {
                image_url: FakeResponse(
                    headers={"Content-Type": "image/bmp"},
                    chunks=[b"bitmap"],
                )
            }
        )

        class FakeConverter:
            def __init__(self):
                self.converted_paths = []

            def should_convert(self, file_path: str) -> bool:
                return file_path.endswith(".bmp")

            def convert_file(self, file_path: str, make_unique_path=None):
                del make_unique_path
                compatible_path = file_path.replace(".bmp", "_compatible.jpg")
                Path(compatible_path).write_bytes(b"jpg")
                self.converted_paths.append((file_path, compatible_path))
                return compatible_path

        converter = FakeConverter()

        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = ImageDownloader(
                session,
                "https://example.com/page",
                temp_dir,
                auto_convert=True,
                converter=converter,
            )
            status_updates = []

            summary = downloader.download_images(
                [image_url],
                status_callback=status_updates.append,
            )

            self.assertEqual(summary.success_count, 1)
            self.assertEqual(summary.converted_count, 1)
            self.assertEqual(status_updates, ["正在下载：1/1", "正在转码：1/1"])
            self.assertTrue(converter.converted_paths)
            self.assertTrue(Path(converter.converted_paths[0][1]).exists())

    def test_download_image_prefers_upgraded_original_candidate(self):
        thumbnail_url = "https://img.example.com/uploads/photo-300x200.jpg?width=300&height=200"
        original_url = "https://img.example.com/uploads/photo.jpg"
        session = FakeSession(
            {
                original_url: FakeResponse(
                    headers={"Content-Type": "image/jpeg"},
                    chunks=[b"original"],
                    url=original_url,
                ),
            }
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = ImageDownloader(session, "https://example.com/page", temp_dir)
            saved_path = downloader.download_image(thumbnail_url)

            self.assertEqual(session.calls[0]["url"], original_url)
            self.assertEqual(Path(saved_path).name, "photo.jpg")
            self.assertTrue(Path(saved_path).exists())

    def test_download_image_strips_post_extension_processing_suffix(self):
        preview_url = (
            "https://img.example.com/uploads/photo.JPG"
            "~tplv-9lv23dm2t1-resize-animforce-v1:480:1000:gif.avif?sign=abc"
        )
        original_url = "https://img.example.com/uploads/photo.JPG?sign=abc"
        session = FakeSession(
            {
                original_url: FakeResponse(
                    headers={"Content-Type": "image/jpeg"},
                    chunks=[b"original"],
                    url=original_url,
                ),
            }
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = ImageDownloader(session, "https://example.com/page", temp_dir)
            saved_path = downloader.download_image(preview_url)

            self.assertEqual(session.calls[0]["url"], original_url)
            self.assertEqual(Path(saved_path).name, "photo.JPG")
            self.assertTrue(Path(saved_path).exists())


if __name__ == "__main__":
    unittest.main()
