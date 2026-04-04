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
            if not full_url:
                return
            if self.is_unwanted_image(full_url):
                return
            if full_url not in seen:
                seen.add(full_url)
                found.append(full_url)

        lazy_attrs = [
            "data-original",
            "data-src",
            "data-lazy-src",
            "data-image",
            "data-url",
            "data-echo",
            "data-lazy",
            "data-flickity-lazyload",
            "src",
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
            if href and self.looks_like_image(href) and not self.is_unwanted_image(href):
                add_url(href)

        for tag in soup.find_all(style=True):
            style = tag.get("style") or ""
            for bg_url in self.extract_urls_from_style(style):
                add_url(bg_url)

        # meta_selectors = [
        #     {"property": "og:image"},
        #     {"name": "twitter:image"},
        #     {"itemprop": "image"},
        # ]
        # for selector in meta_selectors:
        #     for meta in soup.find_all("meta", attrs=selector):
        #         add_url(meta.get("content"))

        # for link in soup.find_all("link", href=True):
        #     rel = link.get("rel", [])
        #     if isinstance(rel, list):
        #         rel_text = " ".join(rel).lower()
        #     else:
        #         rel_text = str(rel).lower()

        #     href = link.get("href")
        #     if "icon" in rel_text or "image" in rel_text or self.looks_like_image(href or ""):
        #         add_url(href)

        return found

    def parse_srcset(self, srcset_value: str):
        candidates = []

        for item in srcset_value.split(","):
            parts = item.strip().split()
            if not parts:
                continue

            url = parts[0].strip()
            score = 0

            if len(parts) > 1:
                descriptor = parts[1].strip().lower()
                if descriptor.endswith("w"):
                    try:
                        score = int(descriptor[:-1])
                    except ValueError:
                        score = 0
                elif descriptor.endswith("x"):
                    try:
                        score = float(descriptor[:-1]) * 1000
                    except ValueError:
                        score = 0

            candidates.append((score, url))

        if not candidates:
            return []

        candidates.sort(key=lambda x: x[0], reverse=True)
        return [candidates[0][1]]
    
    def normalize_image_url(self, raw_url: str, base_url: str):
        if not raw_url:
            return None

        raw_url = raw_url.strip().strip("\"'")
        if raw_url.startswith("data:"):
            return None
        
        if raw_url.startswith(("data:", "javascript:", "#", "about:")):
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
                ".tiff",
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
    
    def is_unwanted_image(self, url: str) -> bool:
        lowered = url.lower()
        blocked_keywords = [
            "icon", "logo", "avatar", "favicon", "sprite", "badge", "thumb", "thumbnail"
        ]
        blocked_sizes = [
            "16x16", "24x24", "32x32", "48x48", "64x64", "96x96", "128x128"
        ]

        return any(word in lowered for word in blocked_keywords + blocked_sizes)