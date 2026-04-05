import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from utils.helpers import (
    UNWANTED_IMAGE_KEYWORDS,
    UNWANTED_IMAGE_SIZE_HINTS,
    VALID_IMAGE_EXTENSIONS,
    setup_logger,
)


class ImageExtractor:
    HIGH_PRIORITY_IMAGE_ATTRS = [
        ("data-full", 320),
        ("data-full-src", 320),
        ("data-zoom-image", 320),
        ("data-zoom-src", 320),
        ("data-hires", 280),
        ("data-large-file", 280),
        ("data-orig-file", 280),
        ("data-original", 260),
        ("data-src-large", 240),
        ("data-large", 220),
        ("data-image", 200),
        ("data-src", 180),
        ("data-lazy-src", 160),
        ("data-url", 140),
        ("data-echo", 120),
        ("data-lazy", 120),
        ("data-flickity-lazyload", 200),
        ("src", 100),
    ]
    GENERIC_IMAGE_ATTR_KEYWORDS = (
        "origin",
        "original",
        "master",
        "download",
        "raw",
        "full",
        "zoom",
        "hires",
        "large",
        "big",
        "src",
        "image",
        "img",
        "photo",
        "poster",
        "url",
        "file",
        "href",
    )
    IGNORED_GENERIC_ATTRS = {
        "alt",
        "class",
        "decoding",
        "height",
        "loading",
        "sizes",
        "style",
        "title",
        "width",
    }
    IMAGE_EXTENSION_PATTERN = "|".join(
        sorted(
            {re.escape(ext.lstrip(".")) for ext in VALID_IMAGE_EXTENSIONS},
            key=len,
            reverse=True,
        )
    )
    RESIZE_QUERY_KEYS = frozenset(
        {
            "w",
            "width",
            "h",
            "height",
            "fit",
            "crop",
            "resize",
            "size",
            "quality",
            "q",
            "dpr",
            "imgmax",
            "maxwidth",
            "maxheight",
        }
    )

    def __init__(self, session):
        self.session = session
        self.logger = setup_logger()

    def fetch_html(self, url: str) -> str:
        if self.session is None:
            raise ValueError("当前提取器没有可用的 HTTP 会话。")

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
        ranked_images = {}
        ordered_keys = []

        def add_url(candidate, score=0):
            full_url = self.normalize_image_url(candidate, base_url)
            if not full_url:
                return
            if self.is_unwanted_image(full_url):
                return

            identity = self.build_image_identity(full_url)
            final_score = score + self.score_image_candidate_url(full_url)
            existing = ranked_images.get(identity)

            if existing is None:
                ordered_keys.append(identity)
                ranked_images[identity] = {"url": full_url, "score": final_score}
                return

            if final_score > existing["score"]:
                ranked_images[identity] = {"url": full_url, "score": final_score}

        for img in soup.find_all("img"):
            for attr, base_score in self.HIGH_PRIORITY_IMAGE_ATTRS:
                add_url(img.get(attr), score=base_score)

            for candidate, base_score in self.iter_generic_image_attr_candidates(img):
                add_url(candidate, score=base_score)

            srcset_candidate = self.pick_best_srcset_candidate(
                img.get("srcset") or img.get("data-srcset")
            )
            if srcset_candidate:
                item, srcset_score = srcset_candidate
                add_url(item, score=220 + srcset_score)

            wrapped_link = img.find_parent("a", href=True)
            if wrapped_link and self.looks_like_image(wrapped_link.get("href") or ""):
                add_url(wrapped_link.get("href"), score=300)

        for source in soup.find_all("source"):
            for candidate, base_score in self.iter_generic_image_attr_candidates(source):
                add_url(candidate, score=base_score)

            srcset_candidate = self.pick_best_srcset_candidate(
                source.get("srcset") or source.get("data-srcset")
            )
            if srcset_candidate:
                item, srcset_score = srcset_candidate
                add_url(item, score=220 + srcset_score)

        for a in soup.find_all("a", href=True):
            href = self.normalize_image_url(a.get("href"), base_url)
            if href and self.looks_like_image(href) and not self.is_unwanted_image(href):
                add_url(href, score=260)

        for tag in soup.find_all(style=True):
            style = tag.get("style") or ""
            for bg_url in self.extract_urls_from_style(style):
                add_url(bg_url, score=120)

        meta_selectors = [
            {"property": "og:image"},
            {"name": "twitter:image"},
            {"itemprop": "image"},
        ]
        for selector in meta_selectors:
            for meta in soup.find_all("meta", attrs=selector):
                add_url(meta.get("content"), score=160)

        for link in soup.find_all("link", href=True):
            rel = link.get("rel", [])
            rel_text = " ".join(rel).lower() if isinstance(rel, list) else str(rel).lower()
            href = link.get("href")
            if "icon" in rel_text or "image" in rel_text or self.looks_like_image(href or ""):
                add_url(href, score=80)

        return [ranked_images[key]["url"] for key in ordered_keys]

    def parse_srcset(self, srcset_value: str):
        best_candidate = self.pick_best_srcset_candidate(srcset_value)
        if not best_candidate:
            return []
        best_url, _ = best_candidate
        return [best_url]

    def parse_srcset_candidates(self, srcset_value: str):
        candidates = []
        if not srcset_value:
            return candidates

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
                        score = int(float(descriptor[:-1]) * 1000)
                    except ValueError:
                        score = 0

            candidates.append((url, score))

        return candidates

    def pick_best_srcset_candidate(self, srcset_value: str):
        candidates = self.parse_srcset_candidates(srcset_value)
        if not candidates:
            return None
        return max(candidates, key=lambda item: item[1])

    def normalize_image_url(self, raw_url: str, base_url: str):
        if not raw_url:
            return None

        raw_url = raw_url.strip().strip("\"'")
        if raw_url.startswith(("data:", "javascript:", "#", "about:")):
            return None

        if raw_url.startswith("//"):
            raw_url = "https:" + raw_url

        full_url = urljoin(base_url, raw_url)
        parsed = urlparse(full_url)

        if parsed.scheme not in {"http", "https"}:
            return None

        return full_url

    def build_image_identity(self, image_url: str) -> str:
        parsed = urlparse(image_url)
        normalized_path = self.strip_resize_suffix(
            self.strip_post_extension_transform_suffix(parsed.path)
        )
        filtered_query = self.filter_resize_query(parsed.query)
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                normalized_path,
                parsed.params,
                filtered_query,
                "",
            )
        )

    def strip_resize_suffix(self, path: str) -> str:
        return re.sub(r"([_-])\d{2,5}x\d{2,5}(?=\.[a-z0-9]+$)", "", path, flags=re.IGNORECASE)

    def strip_post_extension_transform_suffix(self, path: str) -> str:
        pattern = rf"(\.(?:{self.IMAGE_EXTENSION_PATTERN}))(?:[~!@].+)$"
        return re.sub(pattern, r"\1", path, flags=re.IGNORECASE)

    def filter_resize_query(self, query: str) -> str:
        if not query:
            return ""

        filtered_pairs = [
            (key, value)
            for key, value in parse_qsl(query, keep_blank_values=True)
            if key.lower() not in self.RESIZE_QUERY_KEYS
        ]
        return urlencode(filtered_pairs, doseq=True)

    def score_image_candidate_url(self, image_url: str) -> int:
        parsed = urlparse(image_url)
        path_bonus = self.extract_size_score_from_path(parsed.path)
        query_bonus = self.extract_size_score_from_query(parsed.query)
        return min(max(path_bonus, query_bonus) // 10, 180)

    def extract_size_score_from_path(self, path: str) -> int:
        path = self.strip_post_extension_transform_suffix(path)
        match = re.search(r"(\d{2,5})x(\d{2,5})(?=\.[a-z0-9]+$)", path, flags=re.IGNORECASE)
        if not match:
            return 0
        return max(int(match.group(1)), int(match.group(2)))

    def extract_size_score_from_query(self, query: str) -> int:
        size_values = []
        for key, value in parse_qsl(query, keep_blank_values=True):
            if key.lower() in {"w", "width", "h", "height"} and value.isdigit():
                size_values.append(int(value))
        return max(size_values, default=0)

    def looks_like_image(self, url: str) -> bool:
        path = urlparse(url).path.lower()
        if any(path.endswith(ext) for ext in VALID_IMAGE_EXTENSIONS):
            return True

        stripped_path = self.strip_post_extension_transform_suffix(path)
        return any(stripped_path.endswith(ext) for ext in VALID_IMAGE_EXTENSIONS)

    def iter_generic_image_attr_candidates(self, tag):
        known_attrs = {attr for attr, _ in self.HIGH_PRIORITY_IMAGE_ATTRS}
        known_attrs.update({"srcset", "data-srcset"})

        for attr_name, attr_value in tag.attrs.items():
            normalized_attr_name = str(attr_name).lower()

            if (
                normalized_attr_name in known_attrs
                or normalized_attr_name in self.IGNORED_GENERIC_ATTRS
            ):
                continue

            if "srcset" in normalized_attr_name:
                best_candidate = self.pick_best_srcset_candidate(self.stringify_attr_value(attr_value))
                if best_candidate and self.looks_like_image_reference(best_candidate[0]):
                    item, srcset_score = best_candidate
                    yield item, self.score_generic_image_attr_name(normalized_attr_name) + srcset_score
                continue

            if not self.looks_like_image_attr_name(normalized_attr_name):
                continue

            for item in self.expand_attr_values(attr_value):
                if self.looks_like_image_reference(item):
                    yield item, self.score_generic_image_attr_name(normalized_attr_name)

    def expand_attr_values(self, attr_value):
        if isinstance(attr_value, (list, tuple)):
            return [str(item).strip() for item in attr_value if isinstance(item, str) and item.strip()]
        if isinstance(attr_value, str) and attr_value.strip():
            return [attr_value.strip()]
        return []

    def stringify_attr_value(self, attr_value):
        if isinstance(attr_value, (list, tuple)):
            return ", ".join(str(item) for item in attr_value if isinstance(item, str))
        if isinstance(attr_value, str):
            return attr_value
        return ""

    def looks_like_image_attr_name(self, attr_name: str) -> bool:
        return any(keyword in attr_name for keyword in self.GENERIC_IMAGE_ATTR_KEYWORDS)

    def looks_like_image_reference(self, value: str) -> bool:
        lowered = value.strip().lower()
        if not lowered:
            return False
        if lowered.startswith(("http://", "https://", "//", "/", "./", "../")):
            return True
        if re.search(rf"\.(?:{self.IMAGE_EXTENSION_PATTERN})(?:$|[?#~!@])", lowered):
            return True
        return False

    def score_generic_image_attr_name(self, attr_name: str) -> int:
        if any(keyword in attr_name for keyword in ("origin", "original", "master", "download", "raw")):
            return 340
        if any(keyword in attr_name for keyword in ("full", "zoom", "hires")):
            return 300
        if any(keyword in attr_name for keyword in ("large", "big", "poster")):
            return 240
        if any(keyword in attr_name for keyword in ("src", "image", "img", "photo")):
            return 180
        if any(keyword in attr_name for keyword in ("url", "file", "href")):
            return 160
        return 120

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
        blocked_markers = UNWANTED_IMAGE_KEYWORDS + UNWANTED_IMAGE_SIZE_HINTS
        return any(marker in lowered for marker in blocked_markers)
