import os
from datetime import datetime
from urllib.parse import urlparse
import requests
from PyQt5.QtCore import QThread, pyqtSignal

from scraper.extractor import ImageExtractor
from scraper.downloader import ImageDownloader
from utils.helpers import USER_AGENT


class ImageScraperThread(QThread):
    progress_changed = pyqtSignal(int)
    status_changed = pyqtSignal(str)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, page_url: str, save_dir: str, mode: str = "static", image_urls=None, parent=None):
        super().__init__(parent)
        self.page_url = page_url.strip()
        self.base_save_dir = save_dir
        self.save_dir = self.prepare_task_save_dir(save_dir)
        self.mode = mode
        self.image_urls = image_urls

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

        self.downloader = ImageDownloader(self.session, self.page_url, self.save_dir)

    def run(self):
        try:
            self.status_changed.emit("正在获取网页内容...")

            if self.image_urls is not None:
                image_urls = self.image_urls
            else:
                extractor = ImageExtractor(self.session)
                image_urls = extractor.extract_from_page(self.page_url)

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

    def prepare_task_save_dir(self, base_dir: str) -> str:
        parsed = urlparse(self.page_url)
        domain = parsed.netloc.replace(".", "_") if parsed.netloc else "image_scraper"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder_name = f"{domain}_{timestamp}"

        final_dir = os.path.join(base_dir, folder_name)
        os.makedirs(final_dir, exist_ok=True)
        return final_dir