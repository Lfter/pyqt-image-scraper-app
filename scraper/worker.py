import requests
from PyQt5.QtCore import QThread, pyqtSignal

from scraper.extractor import ImageExtractor
from scraper.dynamic_extractor import DynamicImageExtractor
from scraper.downloader import ImageDownloader
from utils.helpers import USER_AGENT
from utils.helpers import USER_AGENT, setup_logger


class ImageScraperThread(QThread):
    progress_changed = pyqtSignal(int)
    status_changed = pyqtSignal(str)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, page_url: str, save_dir: str, mode: str = "static", parent=None):
        super().__init__(parent)
        self.page_url = page_url.strip()
        self.save_dir = save_dir
        self.mode = mode

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

        self.extractor = ImageExtractor(self.session)
        self.downloader = ImageDownloader(self.session, self.page_url, self.save_dir)
        self.logger = setup_logger()

    def run(self):
        try:
            self.status_changed.emit("正在获取网页内容...")

            if self.mode == "dynamic":
                self.extractor = DynamicImageExtractor()

                session = requests.Session()
                session.headers.update({"User-Agent": USER_AGENT})
                self.downloader = ImageDownloader(session, self.page_url, self.save_dir)
            else:
                session = requests.Session()
                session.headers.update({"User-Agent": USER_AGENT})

                self.extractor = ImageExtractor(session)
                self.downloader = ImageDownloader(session, self.page_url, self.save_dir)

            image_urls = self.extractor.extract_from_page(self.page_url)

            if not image_urls:
                raise ValueError("没有在该网页中找到可下载的图片。")

            self.status_changed.emit(f"共发现 {len(image_urls)} 张图片，开始下载...")

            success_count = self.downloader.download_images(
                image_urls,
                progress_callback=self.progress_changed.emit,
                status_callback=self.status_changed.emit,
            )

            self.progress_changed.emit(100)
            self.finished_ok.emit(f"抓取完成，共下载 {success_count} 张图片。")

        except Exception as exc:
            self.failed.emit(str(exc))