import os
from datetime import datetime
from urllib.parse import urlparse

import requests
from PyQt5.QtCore import QThread, pyqtSignal

from scraper.downloader import DownloadSummary, ImageDownloader
from scraper.extractor import ImageExtractor
from utils.helpers import USER_AGENT


class ImageScraperThread(QThread):
    TRANSFORMED_URL_MARKERS = (
        "~",
        "resize",
        "thumbnail",
        "thumb",
        "preview",
        "crop",
        "fit=",
        "width=",
        "height=",
        "imagex",
    )

    progress_changed = pyqtSignal(int)
    status_changed = pyqtSignal(str)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        page_url: str,
        save_dir: str,
        mode: str = "static",
        image_urls=None,
        auto_convert: bool = False,
        keep_original: bool = True,
        session=None,
        extractor_factory=ImageExtractor,
        downloader_cls=ImageDownloader,
        now_provider=None,
        browser_extractor_factory=None,
        parent=None,
    ):
        super().__init__(parent)
        self.page_url = page_url.strip()
        self.mode = mode
        self.image_urls = image_urls
        self.auto_convert = auto_convert
        self.keep_original = keep_original
        self.extractor_factory = extractor_factory
        self.downloader_cls = downloader_cls
        self.now_provider = now_provider or datetime.now
        self.browser_extractor_factory = browser_extractor_factory
        self.save_dir = self.prepare_task_save_dir(save_dir)

        self.session = session or requests.Session()
        if hasattr(self.session, "headers"):
            self.session.headers.update({"User-Agent": USER_AGENT})

        self.downloader = self.downloader_cls(
            self.session,
            self.page_url,
            self.save_dir,
            auto_convert=self.auto_convert,
            keep_original=self.keep_original,
        )

    def run(self):
        try:
            image_urls = self.resolve_image_urls()

            if not image_urls:
                raise ValueError("没有在该网页中找到可下载的图片。")

            self.status_changed.emit(f"共发现 {len(image_urls)} 张图片，开始下载...")

            summary = self.downloader.download_images(
                image_urls,
                progress_callback=self.progress_changed.emit,
                status_callback=self.status_changed.emit,
            )

            self.progress_changed.emit(100)
            self.finished_ok.emit(self.build_finished_message(summary))

        except Exception as exc:
            self.failed.emit(str(exc))

    def resolve_image_urls(self):
        if self.image_urls is not None:
            self.status_changed.emit("正在整理图片链接...")
            return self.merge_image_urls(self.image_urls, [])

        self.status_changed.emit("正在获取网页内容...")
        extractor = self.extractor_factory(self.session)
        image_urls = extractor.extract_from_page(self.page_url)

        if self.mode == "static" and self.should_try_browser_assisted_extraction(image_urls):
            assisted_urls = self.try_browser_assisted_extraction(image_urls)
            if assisted_urls:
                return assisted_urls

        return image_urls

    def should_try_browser_assisted_extraction(self, image_urls) -> bool:
        if not image_urls:
            return True

        transformed_count = sum(1 for item in image_urls if self.is_transformed_image_url(item))
        return transformed_count >= max(1, len(image_urls) // 2)

    def is_transformed_image_url(self, image_url: str) -> bool:
        lowered = image_url.lower()
        return any(marker in lowered for marker in self.TRANSFORMED_URL_MARKERS)

    def try_browser_assisted_extraction(self, fallback_urls):
        try:
            browser_extractor = self.create_browser_extractor()
        except Exception:
            return fallback_urls

        self.status_changed.emit("正在尝试浏览器辅助提取原图链接...")

        try:
            browser_extractor.open_page(self.page_url, headless=True)
            image_urls = browser_extractor.extract_from_current_page(self.page_url)
            self.merge_authenticated_session(browser_extractor.build_authenticated_session())
            if getattr(browser_extractor, "primary_network_image_urls", None):
                return image_urls
            return self.merge_image_urls(image_urls, fallback_urls)
        except Exception:
            return fallback_urls
        finally:
            browser_extractor.close()

    def create_browser_extractor(self):
        if self.browser_extractor_factory is not None:
            return self.browser_extractor_factory()

        from scraper.dynamic_extractor import DynamicImageExtractor

        return DynamicImageExtractor()

    def merge_authenticated_session(self, extra_session):
        if not hasattr(self.session, "cookies") or not hasattr(extra_session, "cookies"):
            return

        for cookie in extra_session.cookies:
            self.session.cookies.set(
                cookie.name,
                cookie.value,
                domain=cookie.domain,
                path=cookie.path,
                secure=cookie.secure,
            )

    def merge_image_urls(self, primary_urls, fallback_urls):
        merged = []
        seen = set()
        identity_builder = ImageExtractor(None)

        for collection in (primary_urls, fallback_urls):
            for image_url in collection:
                identity = identity_builder.build_image_identity(image_url)
                if identity in seen:
                    continue
                seen.add(identity)
                merged.append(image_url)

        return merged

    def prepare_task_save_dir(self, base_dir: str) -> str:
        parsed = urlparse(self.page_url)
        domain = parsed.netloc.replace(".", "_") if parsed.netloc else "image_scraper"

        timestamp = self.now_provider().strftime("%Y%m%d_%H%M%S")
        folder_name = f"{domain}_{timestamp}"

        final_dir = os.path.join(base_dir, folder_name)
        os.makedirs(final_dir, exist_ok=True)
        return final_dir

    def build_finished_message(self, summary) -> str:
        if isinstance(summary, int):
            summary = DownloadSummary(success_count=summary)

        message = f"抓取完成，共下载 {summary.success_count} 张图片。"
        if summary.converted_count:
            message += f" 已生成 {summary.converted_count} 个兼容格式副本。"
        return message
