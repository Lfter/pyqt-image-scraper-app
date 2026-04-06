import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QCoreApplication

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.worker import ImageScraperThread


APP = QCoreApplication.instance() or QCoreApplication([])


class DummySession:
    def __init__(self):
        self.headers = {}


class FakeExtractor:
    last_requested_url = None

    def __init__(self, session):
        self.session = session

    def extract_from_page(self, page_url: str):
        FakeExtractor.last_requested_url = page_url
        return ["https://cdn.example.com/a.jpg"]


class FailIfCalledExtractor:
    def __init__(self, session):
        del session

    def extract_from_page(self, page_url: str):
        raise AssertionError(f"预提取模式不应该再请求页面：{page_url}")


class FakeDownloader:
    instances = []

    def __init__(self, session, page_url, save_dir, auto_convert=False, keep_original=True, converter=None):
        self.session = session
        self.page_url = page_url
        self.save_dir = save_dir
        self.auto_convert = auto_convert
        self.keep_original = keep_original
        self.converter = converter
        self.calls = []
        self.__class__.instances.append(self)

    def download_images(self, image_urls, progress_callback=None, status_callback=None):
        self.calls.append(list(image_urls))
        if progress_callback:
            progress_callback(25)
        if status_callback:
            status_callback(f"正在下载：{len(image_urls)}/{len(image_urls)}")
        return len(image_urls)


class FakeBrowserExtractor:
    def __init__(self):
        self.opened = []
        self.closed = False
        self.primary_network_image_urls = []

    def open_page(self, page_url: str, headless: bool = False):
        self.opened.append((page_url, headless))

    def extract_from_current_page(self, page_url: str):
        del page_url
        return ["https://cdn.example.com/a.jpg"]

    def build_authenticated_session(self):
        return DummySession()

    def close(self):
        self.closed = True


class ImageScraperThreadTests(unittest.TestCase):
    def setUp(self):
        FakeExtractor.last_requested_url = None
        FakeDownloader.instances.clear()

    def test_run_uses_extractor_and_creates_timestamped_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            thread = ImageScraperThread(
                "https://example.com/gallery",
                temp_dir,
                session=DummySession(),
                extractor_factory=FakeExtractor,
                downloader_cls=FakeDownloader,
                now_provider=lambda: datetime(2024, 1, 2, 3, 4, 5),
            )

            progress_updates = []
            status_updates = []
            finished_messages = []
            failed_messages = []

            thread.progress_changed.connect(progress_updates.append)
            thread.status_changed.connect(status_updates.append)
            thread.finished_ok.connect(finished_messages.append)
            thread.failed.connect(failed_messages.append)
            thread.run()

            self.assertEqual(failed_messages, [])
            self.assertEqual(FakeExtractor.last_requested_url, "https://example.com/gallery")
            self.assertTrue(Path(thread.save_dir).exists())
            self.assertTrue(thread.save_dir.endswith("example_com_20240102_030405"))
            self.assertEqual(progress_updates, [25, 100])
            self.assertEqual(status_updates[0], "正在获取网页内容...")
            self.assertIn("共发现 1 张图片，开始下载...", status_updates)
            self.assertEqual(finished_messages, ["抓取完成，共下载 1 张图片。"])
            self.assertEqual(
                FakeDownloader.instances[-1].calls,
                [["https://cdn.example.com/a.jpg"]],
            )
            self.assertFalse(FakeDownloader.instances[-1].auto_convert)

    def test_run_deduplicates_pre_extracted_urls(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            thread = ImageScraperThread(
                "https://example.com/gallery",
                temp_dir,
                image_urls=[
                    "https://cdn.example.com/a.jpg",
                    "https://cdn.example.com/a.jpg",
                    "https://cdn.example.com/b.jpg",
                ],
                session=DummySession(),
                extractor_factory=FailIfCalledExtractor,
                downloader_cls=FakeDownloader,
                now_provider=lambda: datetime(2024, 1, 2, 3, 4, 5),
            )

            status_updates = []
            finished_messages = []

            thread.status_changed.connect(status_updates.append)
            thread.finished_ok.connect(finished_messages.append)
            thread.run()

            self.assertEqual(status_updates[0], "正在整理图片链接...")
            self.assertEqual(
                FakeDownloader.instances[-1].calls,
                [["https://cdn.example.com/a.jpg", "https://cdn.example.com/b.jpg"]],
            )
            self.assertEqual(finished_messages, ["抓取完成，共下载 2 张图片。"])

    def test_run_reports_generated_compatible_copies(self):
        class ConvertingDownloader(FakeDownloader):
            def download_images(self, image_urls, progress_callback=None, status_callback=None):
                del progress_callback, status_callback
                self.calls.append(list(image_urls))

                class Summary:
                    success_count = len(image_urls)
                    converted_count = 1

                return Summary()

        with tempfile.TemporaryDirectory() as temp_dir:
            thread = ImageScraperThread(
                "https://example.com/gallery",
                temp_dir,
                image_urls=["https://cdn.example.com/a.webp"],
                auto_convert=True,
                session=DummySession(),
                extractor_factory=FailIfCalledExtractor,
                downloader_cls=ConvertingDownloader,
                now_provider=lambda: datetime(2024, 1, 2, 3, 4, 5),
            )

            finished_messages = []
            thread.finished_ok.connect(finished_messages.append)
            thread.run()

            self.assertEqual(
                finished_messages,
                ["抓取完成，共下载 1 张图片。 已生成 1 个兼容格式副本。"],
            )
            self.assertTrue(ConvertingDownloader.instances[-1].auto_convert)

    def test_run_tries_browser_assisted_extraction_for_transformed_urls(self):
        class TransformingExtractor:
            def __init__(self, session):
                self.session = session

            def extract_from_page(self, page_url: str):
                del page_url
                return ["https://cdn.example.com/a.jpg~tplv-thumb.avif"]

        browser_instances = []

        def create_browser_extractor():
            extractor = FakeBrowserExtractor()
            browser_instances.append(extractor)
            return extractor

        with tempfile.TemporaryDirectory() as temp_dir:
            thread = ImageScraperThread(
                "https://example.com/gallery",
                temp_dir,
                session=DummySession(),
                extractor_factory=TransformingExtractor,
                downloader_cls=FakeDownloader,
                browser_extractor_factory=create_browser_extractor,
                now_provider=lambda: datetime(2024, 1, 2, 3, 4, 5),
            )

            status_updates = []
            thread.status_changed.connect(status_updates.append)
            thread.run()

            self.assertIn("正在尝试浏览器辅助提取原图链接...", status_updates)
            self.assertEqual(browser_instances[0].opened, [("https://example.com/gallery", True)])
            self.assertTrue(browser_instances[0].closed)
            self.assertEqual(
                FakeDownloader.instances[-1].calls,
                [["https://cdn.example.com/a.jpg"]],
            )

    def test_run_prefers_browser_primary_results_without_merging_fallbacks(self):
        class TransformingExtractor:
            def __init__(self, session):
                self.session = session

            def extract_from_page(self, page_url: str):
                del page_url
                return [
                    "https://cdn.example.com/a.jpg~tplv-thumb.avif",
                    "https://example.com/pic/a.jpg",
                ]

        browser_instances = []

        def create_browser_extractor():
            extractor = FakeBrowserExtractor()
            extractor.primary_network_image_urls = ["https://cdn.example.com/a.jpg"]
            browser_instances.append(extractor)
            return extractor

        with tempfile.TemporaryDirectory() as temp_dir:
            thread = ImageScraperThread(
                "https://example.com/gallery",
                temp_dir,
                session=DummySession(),
                extractor_factory=TransformingExtractor,
                downloader_cls=FakeDownloader,
                browser_extractor_factory=create_browser_extractor,
                now_provider=lambda: datetime(2024, 1, 2, 3, 4, 5),
            )

            thread.run()

            self.assertTrue(browser_instances[0].closed)
            self.assertEqual(
                FakeDownloader.instances[-1].calls,
                [["https://cdn.example.com/a.jpg"]],
            )


if __name__ == "__main__":
    unittest.main()
