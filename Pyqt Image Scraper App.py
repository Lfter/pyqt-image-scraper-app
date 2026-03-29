import os
import re
import sys
import hashlib
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


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

    def run(self):
        try:
            self.status_changed.emit("正在获取网页内容...")
            html = self.fetch_html(self.page_url)
            soup = BeautifulSoup(html, "html.parser")

            image_urls = self.extract_image_urls(soup, self.page_url)
            if not image_urls:
                raise ValueError("没有在该网页中找到可下载的图片。")

            self.status_changed.emit(f"共发现 {len(image_urls)} 张图片，开始下载...")
            self.download_images(image_urls)
            self.progress_changed.emit(100)
            self.finished_ok.emit(f"抓取完成，共下载 {len(image_urls)} 张图片。")
        except Exception as exc:
            self.failed.emit(str(exc))

    def fetch_html(self, url: str) -> str:
        response = self.session.get(url, timeout=20)
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        return response.text

    def extract_image_urls(self, soup: BeautifulSoup, base_url: str):
        found = []
        seen = set()

        def add_url(candidate):
            full_url = self.normalize_image_url(candidate, base_url)
            if full_url and full_url not in seen:
                seen.add(full_url)
                found.append(full_url)

        # 1) 标准 img 标签 + 常见懒加载属性
        lazy_attrs = [
            "src", "data-src", "data-original", "data-lazy-src", "data-url",
            "data-image", "data-echo", "data-lazy", "data-flickity-lazyload"
        ]
        for img in soup.find_all("img"):
            for attr in lazy_attrs:
                add_url(img.get(attr))

            srcset = img.get("srcset") or img.get("data-srcset")
            if srcset:
                for item in self.parse_srcset(srcset):
                    add_url(item)

        # 2) picture / source 标签中的 srcset
        for source in soup.find_all("source"):
            srcset = source.get("srcset") or source.get("data-srcset")
            if srcset:
                for item in self.parse_srcset(srcset):
                    add_url(item)

        # 3) a 标签中直接指向图片的链接
        for a in soup.find_all("a", href=True):
            href = self.normalize_image_url(a.get("href"), base_url)
            if href and self.looks_like_image(href):
                add_url(href)

        # 4) 行内 style 的 background-image
        for tag in soup.find_all(style=True):
            style = tag.get("style") or ""
            for bg_url in self.extract_urls_from_style(style):
                add_url(bg_url)

        # 5) SEO / 社交分享图片
        meta_selectors = [
            {"property": "og:image"},
            {"name": "twitter:image"},
            {"itemprop": "image"},
        ]
        for selector in meta_selectors:
            for meta in soup.find_all("meta", attrs=selector):
                add_url(meta.get("content"))

        # 6) link 标签中的站点图标或图片资源
        for link in soup.find_all("link", href=True):
            rel = " ".join(link.get("rel", [])) if isinstance(link.get("rel"), list) else str(link.get("rel", ""))
            href = link.get("href")
            if "icon" in rel.lower() or "image" in rel.lower() or self.looks_like_image(href or ""):
                add_url(href)

        return found

    def parse_srcset(self, srcset_value: str):
        results = []
        for item in srcset_value.split(","):
            part = item.strip().split(" ")[0].strip()
            if part:
                results.append(part)
        return results

    def normalize_image_url(self, raw_url: str, base_url: str):
        if not raw_url:
            return None
        raw_url = raw_url.strip().strip('"\'')
        if raw_url.startswith("data:"):
            return None
        if raw_url.startswith("//"):
            raw_url = "https:" + raw_url
        full_url = urljoin(base_url, raw_url)
        parsed = urlparse(full_url)
        if parsed.scheme not in {"http", "https"}:
            return None
        return full_url

    def looks_like_image(self, url: str) -> bool:
        path = urlparse(url).path.lower()
        return any(
            path.endswith(ext)
            for ext in [
                ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".tiff", ".ico", ".avif"
            ]
        )

    def extract_urls_from_style(self, style_text: str):
        matches = re.findall(r"url\((.*?)\)", style_text, flags=re.IGNORECASE)
        results = []
        for match in matches:
            cleaned = match.strip().strip('"\'')
            if cleaned:
                results.append(cleaned)
        return results

    def download_images(self, image_urls):
        total = len(image_urls)
        success_count = 0

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
                # 单张图片失败时不中断整体流程
                pass

            progress = int(index / total * 100)
            self.progress_changed.emit(progress)
            self.status_changed.emit(f"正在下载：{index}/{total}")

        if success_count == 0:
            raise ValueError("网页中找到了图片链接，但全部下载失败。")

    def decide_extension(self, image_url: str, content_type: str) -> str:
        path = urlparse(image_url).path
        _, ext = os.path.splitext(path)
        ext = ext.lower()

        valid_exts = {
            ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".tiff", ".ico", ".avif"
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
        if ext in {".bmp"}:
            return "BMP"
        if ext in {".tiff"}:
            return "TIFF"
        if ext in {".ico"}:
            return "ICO"
        if ext in {".avif"}:
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("网页图片抓取工具")
        self.resize(860, 620)
        self.setMinimumSize(760, 520)

        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #eef0f3;
            }
            QWidget {
                font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
            }
            QLineEdit {
                border: 2px solid #d8dde6;
                border-radius: 16px;
                padding: 14px 18px;
                font-size: 18px;
                background: white;
                color: #4a5568;
            }
            QLineEdit:focus {
                border-color: #4a90e2;
            }
            QPushButton {
                background-color: #1f7ae0;
                color: white;
                border: none;
                border-radius: 20px;
                font-size: 22px;
                font-weight: 600;
                padding: 18px 28px;
            }
            QPushButton:hover {
                background-color: #176ccc;
            }
            QPushButton:disabled {
                background-color: #8db8ef;
                color: #edf4ff;
            }
            QProgressBar {
                border: none;
                background: #dfe3e8;
                border-radius: 6px;
                height: 12px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #1f7ae0;
                border-radius: 6px;
            }
            QLabel {
                color: #5a6472;
            }
            """
        )

        central = QWidget()
        self.setCentralWidget(central)

        outer_layout = QVBoxLayout(central)
        outer_layout.setContentsMargins(70, 40, 70, 40)
        outer_layout.setAlignment(Qt.AlignCenter)

        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(
            """
            QFrame#card {
                background: white;
                border-radius: 18px;
            }
            """
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(Qt.gray)
        card.setGraphicsEffect(shadow)

        outer_layout.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(52, 52, 52, 52)
        layout.setSpacing(28)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("请输入网址，例如：https://example.com")
        self.url_input.setMinimumHeight(58)
        layout.addWidget(self.url_input)

        self.status_label = QLabel("0% 正在准备...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addSpacing(8)
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMinimumHeight(12)
        layout.addWidget(self.progress_bar)

        layout.addSpacing(30)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addStretch()
        layout.addLayout(button_row)

        self.start_button = QPushButton("开始抓取")
        self.start_button.setFixedSize(360, 92)
        self.start_button.clicked.connect(self.choose_folder_and_start)
        button_row.addWidget(self.start_button, alignment=Qt.AlignCenter)

        layout.addStretch()

    def choose_folder_and_start(self):
        page_url = self.url_input.text().strip()
        if not page_url:
            QMessageBox.warning(self, "提示", "请先输入网页地址。")
            return

        if not page_url.startswith(("http://", "https://")):
            page_url = "https://" + page_url
            self.url_input.setText(page_url)

        save_dir = QFileDialog.getExistingDirectory(self, "选择图片保存文件夹")
        if not save_dir:
            return

        self.progress_bar.setValue(0)
        self.status_label.setText("0% 正在准备...")
        self.start_button.setEnabled(False)
        self.url_input.setEnabled(False)

        self.worker = ImageScraperThread(page_url, save_dir)
        self.worker.progress_changed.connect(self.on_progress_changed)
        self.worker.status_changed.connect(self.on_status_changed)
        self.worker.finished_ok.connect(self.on_finished_ok)
        self.worker.failed.connect(self.on_failed)
        self.worker.start()

    def on_progress_changed(self, value: int):
        self.progress_bar.setValue(value)

    def on_status_changed(self, text: str):
        current = self.progress_bar.value()
        if text.startswith("正在下载") or text.startswith("正在获取") or text.startswith("共发现"):
            self.status_label.setText(f"{current}% {text}")
        else:
            self.status_label.setText(text)

    def on_finished_ok(self, message: str):
        self.start_button.setEnabled(True)
        self.url_input.setEnabled(True)
        self.status_label.setText("100% 抓取完成")
        QMessageBox.information(self, "完成", message)

    def on_failed(self, error_message: str):
        self.start_button.setEnabled(True)
        self.url_input.setEnabled(True)
        self.status_label.setText("抓取失败")
        QMessageBox.critical(self, "错误", error_message)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
