import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from utils.helpers import setup_logger


class ImageExtractor:
    def __init__(self, session):
        self.session = session
        self.logger = setup_logger()


    def fetch_html(self, url: str) -> str:
        self.logger.info(f"开始请求网页：{url}")
        response = self.session.get(url, timeout=20)
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        self.logger.info(f"成功获取网页内容，URL: {url}")
        return response.text

    def extract_from_page(self, page_url: str):
        html = self.fetch_html(page_url)
        soup = BeautifulSoup(html, "html.parser")
        image_urls = self.extract_image_urls(soup, page_url)
        self.logger.info(f"图片链接提取完成，共提取 {len(image_urls)} 条链接")
        return image_urls

    def extract_image_urls(self, soup: BeautifulSoup, base_url: str):
        found = []
        seen = set()

        def add_url(candidate):
            full_url = self.normalize_image_url(candidate, base_url)
            if full_url and full_url not in seen:
                seen.add(full_url)
                found.append(full_url)

        lazy_attrs = [
            "src",
            "data-src",
            "data-original",
            "data-lazy-src",
            "data-url",
            "data-image",
            "data-echo",
            "data-lazy",
            "data-flickity-lazyload",
        ]

        for img in soup.find_all("img"):
            for attr in lazy_attrs:
                add_url(img.get(attr))

            srcset = img.get("srcset") or img.get("data-srcset")
            if srcset:
                for item in self.parse_srcset(srcset):
                    add_url(item)

        for source in soup.find_all("source"):
            srcset = source.get("srcset") or source.get("data-srcset")
            if srcset:
                for item in self.parse_srcset(srcset):
                    add_url(item)

        for a in soup.find_all("a", href=True):
            href = self.normalize_image_url(a.get("href"), base_url)
            if href and self.looks_like_image(href):
                add_url(href)

        for tag in soup.find_all(style=True):
            style = tag.get("style") or ""
            for bg_url in self.extract_urls_from_style(style):
                add_url(bg_url)

        meta_selectors = [
            {"property": "og:image"},
            {"name": "twitter:image"},
            {"itemprop": "image"},
        ]
        for selector in meta_selectors:
            for meta in soup.find_all("meta", attrs=selector):
                add_url(meta.get("content"))

        for link in soup.find_all("link", href=True):
            rel = link.get("rel", [])
            if isinstance(rel, list):
                rel_text = " ".join(rel).lower()
            else:
                rel_text = str(rel).lower()

            href = link.get("href")
            if "icon" in rel_text or "image" in rel_text or self.looks_like_image(href or ""):
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

        raw_url = raw_url.strip().strip("\"'")
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
            ]
        )

    def extract_urls_from_style(self, style_text: str):
        matches = re.findall(r"url\((.*?)\)", style_text, flags=re.IGNORECASE)
        results = []

        for match in matches:
            cleaned = match.strip().strip("\"'")
            if cleaned:
                results.append(cleaned)

        return results