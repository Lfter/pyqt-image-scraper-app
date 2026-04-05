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
    def __init__(self, headers=None, chunks=None, error=None):
        self.headers = headers or {}
        self._chunks = chunks or []
        self._error = error

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

            success_count = downloader.download_images(
                [image_url, image_url],
                progress_callback=progress_updates.append,
                status_callback=status_updates.append,
            )

            self.assertEqual(success_count, 2)
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
                success_count = downloader.download_images([good_url, bad_url])
            finally:
                helpers.LOG_DIR = original_log_dir

            self.assertEqual(success_count, 1)
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


if __name__ == "__main__":
    unittest.main()

