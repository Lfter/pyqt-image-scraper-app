import hashlib
import os
import re
from urllib.parse import urlparse, unquote

from utils.helpers import USER_AGENT


class ImageDownloader:
    def __init__(self, session, page_url, save_dir):
        self.session = session
        self.page_url = page_url
        self.save_dir = save_dir

    def download_images(self, image_urls, progress_callback=None, status_callback=None):
        total = len(image_urls)
        success_count = 0

        if total == 0:
            raise ValueError("没有可下载的图片链接。")

        for index, image_url in enumerate(image_urls, start=1):
            try:
                response = self.session.get(
                    image_url,
                    timeout=20,
                    stream=True,
                    headers={"Referer": self.page_url, "User-Agent": USER_AGENT},
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

                with open(file_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

                success_count += 1

            except Exception:
                pass

            progress = int(index / total * 100)

            if progress_callback:
                progress_callback(progress)

            if status_callback:
                status_callback(f"正在下载：{index}/{total}")

        if success_count == 0:
            raise ValueError("网页中找到了图片链接，但全部下载失败。")

        return success_count

    def decide_extension(self, image_url: str, content_type: str) -> str:
        path = urlparse(image_url).path
        _, ext = os.path.splitext(path)
        ext = ext.lower()

        valid_exts = {
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".bmp",
            ".webp",
            ".svg",
            ".tiff",
            ".ico",
            ".avif",
        }

        if ext in valid_exts:
            return ext

        mapping = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/bmp": ".bmp",
            "image/webp": ".webp",
            "image/svg+xml": ".svg",
            "image/tiff": ".tiff",
            "image/x-icon": ".ico",
            "image/vnd.microsoft.icon": ".ico",
            "image/avif": ".avif",
        }

        return mapping.get(content_type.split(";")[0].strip(), ".jpg")

    def classify_image(self, ext: str, content_type: str) -> str:
        ext = ext.lower()

        if ext in {".jpg", ".jpeg"}:
            return "JPEG"
        if ext == ".png":
            return "PNG"
        if ext == ".gif":
            return "GIF"
        if ext == ".webp":
            return "WEBP"
        if ext == ".svg":
            return "SVG"
        if ext == ".bmp":
            return "BMP"
        if ext == ".tiff":
            return "TIFF"
        if ext == ".ico":
            return "ICO"
        if ext == ".avif":
            return "AVIF"
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