import requests
from PyQt5.QtCore import QThread, pyqtSignal

from scraper.extractor import ImageExtractor
from scraper.downloader import ImageDownloader
from utils.helpers import USER_AGENT
from utils.helpers import USER_AGENT, setup_logger


class ImageScraperThread(QThread):
    progress_changed = pyqtSignal(int)
    status_changed = pyqtSignal(str)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, page_url: str, save_dir: str, parent=None):
        super().__init__(parent)
        self.page_url = page_url.strip()
        self.save_dir = save_dir

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

        self.extractor = ImageExtractor(self.session)
        self.downloader = ImageDownloader(self.session, self.page_url, self.save_dir)
        self.logger = setup_logger()

    def run(self):
        try:
            self.logger.info(f"开始抓取任务，页面地址：{self.page_url}，保存目录：{self.save_dir}")
            self.status_changed.emit("正在获取网页内容...")

            image_urls = self.extractor.extract_from_page(self.page_url)

            if not image_urls:
                self.logger.info(f"页面提取完成，共发现 {len(image_urls)} 张图片")
                raise ValueError("没有在该网页中找到可下载的图片。")

            self.status_changed.emit(f"共发现 {len(image_urls)} 张图片，开始下载...")

            success_count = self.downloader.download_images(
                image_urls,
                progress_callback=self.progress_changed.emit,
                status_callback=self.status_changed.emit,
            )
            self.logger.info(f"下载完成，成功下载 {success_count} 张图片")
            self.progress_changed.emit(100)
            self.finished_ok.emit(f"抓取完成，共下载 {success_count} 张图片。")

        except Exception as exc:
            self.logger.exception(f"抓取过程中发生错误：{str(exc)}")
            self.failed.emit(str(exc))