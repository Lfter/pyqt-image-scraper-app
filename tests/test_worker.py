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
from tests.support.fakes import DummySession


APP = QCoreApplication.instance() or QCoreApplication([])


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


class RecordingPipeline:
    last_init_kwargs = None

    def __init__(self, **kwargs):
        self.__class__.last_init_kwargs = kwargs

    def resolve(self, page_url: str, mode: str = "static", image_urls=None):
        del page_url, mode, image_urls
        return ["https://cdn.example.com/a.jpg"]


class ImageScraperThreadTests(unittest.TestCase):
    def setUp(self):
        FakeExtractor.last_requested_url = None
        FakeDownloader.instances.clear()
        RecordingPipeline.last_init_kwargs = None

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

    def test_create_pipeline_passes_adapter_registry(self):
        adapter_registry = object()

        with tempfile.TemporaryDirectory() as temp_dir:
            thread = ImageScraperThread(
                "https://example.com/gallery",
                temp_dir,
                session=DummySession(),
                downloader_cls=FakeDownloader,
                pipeline_cls=RecordingPipeline,
                adapter_registry=adapter_registry,
                now_provider=lambda: datetime(2024, 1, 2, 3, 4, 5),
            )

            image_urls = thread.resolve_image_urls()

            self.assertEqual(image_urls, ["https://cdn.example.com/a.jpg"])
            self.assertIs(RecordingPipeline.last_init_kwargs["adapter_registry"], adapter_registry)


if __name__ == "__main__":
    unittest.main()
