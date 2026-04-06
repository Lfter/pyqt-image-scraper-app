import re
from urllib.parse import parse_qsl, urlparse

from bs4 import BeautifulSoup

from scraper.models import ExtractionResult
from scraper.original_resolver import OriginalImageResolver
from utils.helpers import (
    UNWANTED_IMAGE_KEYWORDS,
    UNWANTED_IMAGE_SIZE_HINTS,
    setup_logger,
)


class ImageExtractor:
    IMAGE_EXTENSION_PATTERN = OriginalImageResolver.IMAGE_EXTENSION_PATTERN
    RESIZE_QUERY_KEYS = OriginalImageResolver.RESIZE_QUERY_KEYS
    IDENTITY_IGNORED_QUERY_KEYS = OriginalImageResolver.IDENTITY_IGNORED_QUERY_KEYS
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
    PAYLOAD_IMAGE_FIELD_KEYWORDS = (
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
        "small",
        "middle",
        "preview",
        "thumb",
        "thumbnail",
        "image",
        "img",
        "pic",
        "photo",
        "cover",
        "poster",
        "logo",
        "background",
        "banner",
        "grid_pic",
    )
    PAYLOAD_IGNORED_FIELD_KEYWORDS = (
        "head",
        "avatar",
        "face_album",
        "face_albums",
        "activity_url",
        "share",
        "wximg",
        "wx_img",
        "qr",
        "qrcode",
        "qr_code",
        "code_url",
        "link",
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

    def __init__(self, session, resolver=None):
        self.session = session
        self.resolver = resolver or OriginalImageResolver()
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

    def extract_result_from_page(self, page_url: str):
        html = self.fetch_html(page_url)
        soup = BeautifulSoup(html, "html.parser")
        candidates = self.extract_image_candidates(soup, page_url)
        self.logger.info(f"图片链接提取完成，共提取 {len(candidates)} 条链接")
        return ExtractionResult(candidates=candidates)

    def extract_from_page(self, page_url: str):
        return self.extract_result_from_page(page_url).image_urls

    def extract_image_candidates(self, soup: BeautifulSoup, base_url: str, source: str = "dom"):
        ranked_images = {}
        ordered_keys = []

        def add_url(candidate, score=0, context=""):
            candidate_obj = self.build_candidate(
                candidate,
                base_url,
                score=score,
                source=source,
                context=context,
            )
            if candidate_obj is None:
                return
            if self.is_unwanted_image(candidate_obj.url):
                return

            self.store_ranked_candidate(ranked_images, ordered_keys, candidate_obj)

        for img in soup.find_all("img"):
            for attr, base_score in self.HIGH_PRIORITY_IMAGE_ATTRS:
                add_url(img.get(attr), score=base_score, context=attr)

            for candidate, base_score in self.iter_generic_image_attr_candidates(img):
                add_url(candidate, score=base_score, context="generic-attr")

            srcset_candidate = self.pick_best_srcset_candidate(
                img.get("srcset") or img.get("data-srcset")
            )
            if srcset_candidate:
                item, srcset_score = srcset_candidate
                add_url(item, score=220 + srcset_score, context="srcset")

            wrapped_link = img.find_parent("a", href=True)
            if wrapped_link and self.looks_like_image(wrapped_link.get("href") or ""):
                add_url(wrapped_link.get("href"), score=300, context="wrapped-link")

        for source_tag in soup.find_all("source"):
            for candidate, base_score in self.iter_generic_image_attr_candidates(source_tag):
                add_url(candidate, score=base_score, context="source-attr")

            srcset_candidate = self.pick_best_srcset_candidate(
                source_tag.get("srcset") or source_tag.get("data-srcset")
            )
            if srcset_candidate:
                item, srcset_score = srcset_candidate
                add_url(item, score=220 + srcset_score, context="source-srcset")

        for a in soup.find_all("a", href=True):
            href = self.normalize_image_url(a.get("href"), base_url)
            if href and self.looks_like_image(href) and not self.is_unwanted_image(href):
                add_url(href, score=260, context="anchor")

        for tag in soup.find_all(style=True):
            style = tag.get("style") or ""
            for bg_url in self.extract_urls_from_style(style):
                add_url(bg_url, score=120, context="style")

        meta_selectors = [
            {"property": "og:image"},
            {"name": "twitter:image"},
            {"itemprop": "image"},
        ]
        for selector in meta_selectors:
            for meta in soup.find_all("meta", attrs=selector):
                add_url(meta.get("content"), score=160, context="meta")

        for link in soup.find_all("link", href=True):
            rel = link.get("rel", [])
            rel_text = " ".join(rel).lower() if isinstance(rel, list) else str(rel).lower()
            href = link.get("href")
            if "icon" in rel_text or "image" in rel_text or self.looks_like_image(href or ""):
                add_url(href, score=80, context="link")

        return [ranked_images[key] for key in ordered_keys]

    def extract_image_urls(self, soup: BeautifulSoup, base_url: str):
        return [candidate.url for candidate in self.extract_image_candidates(soup, base_url)]

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
        return self.resolver.normalize_url(raw_url, base_url)

    def build_image_identity(self, image_url: str) -> str:
        return self.resolver.build_image_identity(image_url)

    def strip_resize_suffix(self, path: str) -> str:
        return self.resolver.strip_resize_suffix(path)

    def strip_post_extension_transform_suffix(self, path: str) -> str:
        return self.resolver.strip_post_extension_transform_suffix(path)

    def filter_resize_query(self, query: str) -> str:
        return self.resolver.filter_resize_query(query)

    def filter_identity_query(self, query: str) -> str:
        return self.resolver.filter_identity_query(query)

    def score_image_candidate_url(self, image_url: str) -> int:
        return self.resolver.score_image_candidate_url(image_url)

    def extract_size_score_from_path(self, path: str) -> int:
        return self.resolver.extract_size_score_from_path(path)

    def extract_size_score_from_query(self, query: str) -> int:
        return self.resolver.extract_size_score_from_query(query)

    def looks_like_image(self, url: str) -> bool:
        return self.resolver.looks_like_image(url)

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

    def looks_like_payload_image_value(self, value: str) -> bool:
        raw_value = value.strip()
        if not raw_value:
            return False
        if "/" not in raw_value and not raw_value.startswith(("http://", "https://", "//", "./", "../")):
            return False
        normalized = self.normalize_image_url(value, "https://example.invalid")
        if not normalized:
            return False
        return self.looks_like_image(normalized)

    def extract_payload_candidates(self, payload, base_url: str, source: str = "payload"):
        ranked_images = {}
        ordered_keys = []

        def add_url(candidate, score=0, context="", is_primary=False):
            candidate_obj = self.build_candidate(
                candidate,
                base_url,
                score=score,
                source=source,
                context=context,
                is_primary=is_primary,
            )
            if candidate_obj is None:
                return
            if self.is_unwanted_image(candidate_obj.url):
                return

            self.store_ranked_candidate(ranked_images, ordered_keys, candidate_obj)

        def walk(node, path_segments):
            if isinstance(node, dict):
                for key, value in node.items():
                    key_text = str(key)
                    walk(value, path_segments + (key_text,))
                return

            if isinstance(node, list):
                for item in node:
                    walk(item, path_segments)
                return

            if (
                isinstance(node, str)
                and self.looks_like_payload_image_value(node)
                and self.looks_like_payload_image_field(path_segments)
            ):
                payload_score = self.score_payload_path(path_segments)
                add_url(
                    node,
                    score=payload_score,
                    context=".".join(path_segments),
                    is_primary=payload_score >= 420,
                )

        walk(payload, tuple())
        return [ranked_images[key] for key in ordered_keys]

    def extract_image_urls_from_payload(self, payload, base_url: str):
        return [candidate.url for candidate in self.extract_payload_candidates(payload, base_url)]

    def score_payload_path(self, path_segments) -> int:
        if not path_segments:
            return 120

        path_text = " ".join(segment.lower() for segment in path_segments)

        if any(keyword in path_text for keyword in ("origin", "original", "master", "download", "raw")):
            return 520
        if any(keyword in path_text for keyword in ("full", "zoom", "hires")):
            return 420
        if any(keyword in path_text for keyword in ("large", "big", "source")):
            return 320
        if any(keyword in path_text for keyword in ("small", "thumb", "thumbnail", "preview", "cover")):
            return 80
        if any(keyword in path_text for keyword in ("image", "img", "pic", "photo", "src")):
            return 220
        return 140

    def looks_like_payload_image_field(self, path_segments) -> bool:
        if not path_segments:
            return False

        path_text = " ".join(segment.lower() for segment in path_segments)
        if any(keyword in path_text for keyword in self.PAYLOAD_IGNORED_FIELD_KEYWORDS):
            return False
        return any(keyword in path_text for keyword in self.PAYLOAD_IMAGE_FIELD_KEYWORDS)

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

    def build_candidate(
        self,
        candidate,
        base_url: str,
        *,
        score: int = 0,
        source: str = "unknown",
        context: str = "",
        is_primary: bool = False,
    ):
        return self.resolver.make_candidate(
            candidate,
            base_url,
            score=score,
            source=source,
            context=context,
            is_primary=is_primary,
        )

    def store_ranked_candidate(self, ranked_images, ordered_keys, candidate):
        existing = ranked_images.get(candidate.identity)

        if existing is None:
            ordered_keys.append(candidate.identity)
            ranked_images[candidate.identity] = candidate
            return

        if self.resolver.is_better_candidate(candidate, existing):
            ranked_images[candidate.identity] = candidate
