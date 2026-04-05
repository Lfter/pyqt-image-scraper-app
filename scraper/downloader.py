from dataclasses import dataclass
import hashlib
import os
import re
from urllib.parse import urlparse, unquote

from scraper.converter import ImageConverter
from utils.helpers import (
    CONTENT_TYPE_TO_EXTENSION,
    IMAGE_CATEGORY_MAP,
    USER_AGENT,
    VALID_IMAGE_EXTENSIONS,
    append_failed_conversion_log,
    append_failed_image_log,
    setup_logger,
)


@dataclass
class DownloadSummary:
    success_count: int
    converted_count: int = 0


class ImageDownloader:
    def __init__(
        self,
        session,
        page_url,
        save_dir,
        auto_convert: bool = False,
        keep_original: bool = True,
        converter=None,
    ):
        self.session = session
        self.logger = setup_logger()
        self.page_url = page_url
        self.save_dir = save_dir
        self.request_headers = {"Referer": self.page_url, "User-Agent": USER_AGENT}
        self.auto_convert = auto_convert
        self.keep_original = keep_original
        self.converter = converter

    def download_images(self, image_urls, progress_callback=None, status_callback=None):
        total = len(image_urls)
        self.logger.info(f"开始下载图片，共 {total} 张")
        success_count = 0
        converted_count = 0

        if total == 0:
            raise ValueError("没有可下载的图片链接。")

        for index, image_url in enumerate(image_urls, start=1):
            try:
                if status_callback:
                    status_callback(f"正在下载：{index}/{total}")

                saved_path = self.download_image(image_url)
                success_count += 1

                if self.auto_convert:
                    converted_count += self.generate_compatible_copy(
                        saved_path,
                        index=index,
                        total=total,
                        status_callback=status_callback,
                    )
            except Exception as exc:
                self.logger.warning(f"图片下载失败：{image_url}，错误：{exc}")
                append_failed_image_log(image_url, exc)

            progress = int(index / total * 100)

            if progress_callback:
                progress_callback(progress)
        failed_count = total - success_count
        self.logger.info(f"下载阶段结束，成功 {success_count} 张，失败 {failed_count} 张")

        if success_count == 0:
            raise ValueError("网页中找到了图片链接，但全部下载失败。")

        return DownloadSummary(success_count=success_count, converted_count=converted_count)

    def generate_compatible_copy(self, file_path: str, index: int, total: int, status_callback=None) -> int:
        converter = self.get_converter()
        if converter is None or not converter.should_convert(file_path):
            return 0

        try:
            if status_callback:
                status_callback(f"正在转码：{index}/{total}")

            converted_path = converter.convert_file(file_path, make_unique_path=self.make_unique_path)
        except Exception as exc:
            self.logger.warning(f"图片转码失败：{file_path}，错误：{exc}")
            append_failed_conversion_log(file_path, exc)
            return 0

        if not converted_path:
            return 0

        self.logger.info("已生成兼容格式副本：%s -> %s", file_path, converted_path)
        return 1

    def get_converter(self):
        if not self.auto_convert:
            return None

        if self.converter is None:
            self.converter = ImageConverter(keep_original=self.keep_original)

        return self.converter

    def download_image(self, image_url: str) -> str:
        response = self.session.get(
            image_url,
            timeout=20,
            stream=True,
            headers=self.request_headers,
        )
        response.raise_for_status()

        content_type = (response.headers.get("Content-Type") or "").lower()
        ext = self.decide_extension(image_url, content_type)
        category = self.classify_image(ext, content_type)

        category_dir = os.path.join(self.save_dir, category)
        os.makedirs(category_dir, exist_ok=True)

        filename = self.build_filename(image_url, ext)
        file_path = os.path.join(category_dir, filename)
        file_path = self.make_unique_path(file_path)

        with open(file_path, "wb") as file_obj:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    file_obj.write(chunk)

        return file_path

    def decide_extension(self, image_url: str, content_type: str) -> str:
        path = urlparse(image_url).path
        _, ext = os.path.splitext(path)
        ext = ext.lower()

        if ext in VALID_IMAGE_EXTENSIONS:
            return ext

        normalized_content_type = content_type.split(";")[0].strip()
        return CONTENT_TYPE_TO_EXTENSION.get(normalized_content_type, ".jpg")

    def classify_image(self, ext: str, content_type: str) -> str:
        ext = ext.lower()
        if ext in IMAGE_CATEGORY_MAP:
            return IMAGE_CATEGORY_MAP[ext]
        if "image" in content_type:
            return "OTHER_IMAGE"

        return "UNKNOWN"

    def build_filename(self, image_url: str, ext: str) -> str:
        path = urlparse(image_url).path
        name = os.path.basename(path)
        name = unquote(name)
        name = re.sub(r"[^\w\-.]+", "_", name)

        if not name or "." not in name:
            digest = hashlib.md5(image_url.encode("utf-8")).hexdigest()[:12]
            name = f"image_{digest}{ext}"
        else:
            root, current_ext = os.path.splitext(name)
            if not current_ext:
                name = root + ext

        return name

    def make_unique_path(self, file_path: str) -> str:
        if not os.path.exists(file_path):
            return file_path

        root, ext = os.path.splitext(file_path)
        counter = 1

        while True:
            new_path = f"{root}_{counter}{ext}"
            if not os.path.exists(new_path):
                return new_path
            counter += 1
