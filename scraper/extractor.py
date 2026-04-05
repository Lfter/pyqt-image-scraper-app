import re
from urllib.parse import urljoin, urlparse, parse_qsl, urlunparse, urlencode

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

        self.logger.info(f"网页请求成功：{url}，状态码：{response.status_code}，HTML长度：{len(response.text)}")
        return response.text

    def extract_from_page(self, page_url: str):
        self.logger.info(f"开始提取页面图片候选：{page_url}")

        html = self.fetch_html(page_url)
        soup = BeautifulSoup(html, "html.parser")

        embedded_candidates = self.extract_candidates_from_embedded_data(html, page_url)
        self.logger.info(f"内嵌数据候选数量：{len(embedded_candidates)}")

        dom_candidates = self.extract_candidates_from_dom(soup, page_url)
        self.logger.info(f"DOM候选数量：{len(dom_candidates)}")

        all_candidates = embedded_candidates + dom_candidates
        self.logger.info(f"候选总数（未归并）：{len(all_candidates)}")

        final_urls = self.merge_and_rank_candidates(all_candidates)
        self.logger.info(f"最终图片URL数量（过滤、归并后）：{len(final_urls)}")
        preview_count = min(10, len(final_urls))
        for i in range(preview_count):
            self.logger.info(f"最终候选[{i+1}]：{final_urls[i]}")

        return final_urls

    def extract_candidates_from_embedded_data(self, html_text: str, base_url: str):
        candidates = []
        self.logger.info("开始从DOM中提取图片候选")

        # 1) 直接从整页文本中提取图片 URL
        url_pattern = re.compile(
            r'https?:\/\/[^\s"\'<>]+?\.(?:jpg|jpeg|png|gif|bmp|webp|tiff|avif)(?:\?[^\s"\'<>]*)?',
            flags=re.IGNORECASE,
        )
        for match in url_pattern.findall(html_text):
            candidate = self.build_candidate(match, "embedded_data", base_url, extra_score=30)
            if candidate:
                candidates.append(candidate)

        # 2) 从 script 中提取更可能是图片字段的内容
        # 这里只做轻量版本，不做 JSON 完整解析
        field_pattern = re.compile(
            r'"(?:url|src|image|original|cover|preview|thumb)"\s*:\s*"([^"]+)"',
            flags=re.IGNORECASE,
        )
        for match in field_pattern.findall(html_text):
            candidate = self.build_candidate(match, "embedded_data_field", base_url, extra_score=20)
            if candidate:
                candidates.append(candidate)

        self.logger.info(f"嵌入数据候选数量：{len(candidates)}")
        return candidates

    def extract_candidates_from_dom(self, soup: BeautifulSoup, base_url: str):
        candidates = []

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
                source_type = f"img_{attr}"
                candidate = self.build_candidate(img.get(attr), source_type, base_url)
                if candidate:
                    candidates.append(candidate)

            srcset = img.get("srcset") or img.get("data-srcset")
            if srcset:
                best_srcset_url = self.parse_srcset(srcset)
                if best_srcset_url:
                    candidate = self.build_candidate(best_srcset_url, "img_srcset_max", base_url, extra_score=15)
                    if candidate:
                        candidates.append(candidate)

        for source in soup.find_all("source"):
            srcset = source.get("srcset") or source.get("data-srcset")
            if srcset:
                best_srcset_url = self.parse_srcset(srcset)
                if best_srcset_url:
                    candidate = self.build_candidate(best_srcset_url, "source_srcset_max", base_url, extra_score=15)
                    if candidate:
                        candidates.append(candidate)

        for a in soup.find_all("a", href=True):
            href = a.get("href")
            if href:
                normalized = self.normalize_image_url(href, base_url)
                if normalized and self.looks_like_image(normalized):
                    candidate = self.build_candidate(normalized, "a_image_href", base_url)
                    if candidate:
                        candidates.append(candidate)

        for tag in soup.find_all(style=True):
            style = tag.get("style") or ""
            for bg_url in self.extract_urls_from_style(style):
                candidate = self.build_candidate(bg_url, "background_image", base_url)
                if candidate:
                    candidates.append(candidate)

        # 默认先不把 meta / link 这类低质量来源作为主来源
        # 如果以后有需要，可以再作为低优先级兜底加回来

        return candidates

    def build_candidate(self, raw_url: str, source_type: str, base_url: str, extra_score: int = 0):
        full_url = self.normalize_image_url(raw_url, base_url)
        if not full_url:
            return None

        # embedded_data 里可能有没后缀但其实是图片的 URL，
        # 所以这里只对非 embedded_data 来源做更严格的扩展名判断
        if not self.looks_like_image(full_url):
            if not source_type.startswith("embedded_data"):
                return None

        if self.is_unwanted_image(full_url):
            return None

        score = self.score_image_candidate(full_url, source_type) + extra_score

        return {
            "url": full_url,
            "source": source_type,
            "score": score,
        }

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
                        score = int(float(descriptor[:-1]) * 1000)
                    except ValueError:
                        score = 0

            candidates.append((score, url))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

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
            "icon",
            "logo",
            "avatar",
            "favicon",
            "sprite",
            "badge",
            "emoji",
            "placeholder",
        ]

        blocked_thumbnail_words = [
            "thumb",
            "thumbnail",
            "small",
            "mini",
            "preview",
        ]

        blocked_sizes = [
            "16x16",
            "24x24",
            "32x32",
            "48x48",
            "64x64",
            "96x96",
            "120x120",
            "128x128",
        ]

        if any(word in lowered for word in blocked_keywords):
            return True

        if any(size in lowered for size in blocked_sizes):
            return True

        # 对缩略图词先做轻度拦截；如果后面误伤太多，可改成只减分不拦截
        if any(word in lowered for word in blocked_thumbnail_words):
            return True

        return False

    def score_image_candidate(self, url: str, source_type: str) -> int:
        lowered = url.lower()

        source_scores = {
            "embedded_data": 80,
            "embedded_data_field": 75,
            "img_data-original": 70,
            "img_data-src": 68,
            "img_data-lazy-src": 66,
            "img_data-image": 64,
            "img_data-url": 62,
            "img_data-echo": 60,
            "img_data-lazy": 60,
            "img_data-flickity-lazyload": 60,
            "img_srcset_max": 58,
            "source_srcset_max": 58,
            "img_src": 45,
            "a_image_href": 42,
            "background_image": 40,
        }

        score = source_scores.get(source_type, 30)

        # 加分项
        if any(ext in lowered for ext in [".jpg", ".jpeg", ".png", ".webp", ".avif"]):
            score += 10

        if any(word in lowered for word in ["original", "raw", "large", "full"]):
            score += 15

        if any(size in lowered for size in ["1080", "1200", "1440", "1600", "1920", "2048"]):
            score += 10

        # 减分项
        if any(word in lowered for word in ["icon", "logo", "avatar", "favicon", "sprite"]):
            score -= 50

        if any(word in lowered for word in ["thumb", "thumbnail", "small", "mini", "preview"]):
            score -= 25

        if any(size in lowered for size in ["16x16", "24x24", "32x32", "48x48", "64x64", "96x96"]):
            score -= 40

        return score

    def normalize_candidate_key(self, url: str):
        parsed = urlparse(url)

        path = parsed.path.lower()

        # 去掉一些常见缩略尺寸后缀
        path = re.sub(r'(_|-)(fw\d+w|fw\d+h|w\d+h\d+|_\d+x\d+)', '', path, flags=re.IGNORECASE)
        path = re.sub(r'(_|-)(thumb|thumbnail|small|mini|preview)', '', path, flags=re.IGNORECASE)

        # 去掉 query 中常见尺寸参数
        query_items = parse_qsl(parsed.query, keep_blank_values=True)
        filtered_query_items = []

        blocked_query_keys = {
            "w", "h", "width", "height", "size", "resize", "x-oss-process",
            "imageview2", "imageMogr2", "thumbnail"
        }

        for key, value in query_items:
            if key.lower() in blocked_query_keys:
                continue
            filtered_query_items.append((key, value))

        normalized_query = urlencode(filtered_query_items, doseq=True)

        normalized = parsed._replace(path=path, query=normalized_query)
        return urlunparse(normalized)

    def merge_and_rank_candidates(self, candidates):
        self.logger.info(f"开始归并候选，输入数量：{len(candidates)}")

        grouped = {}

        for candidate in candidates:
            if not candidate:
                continue

            url = candidate.get("url")
            if not url:
                continue

            key = self.normalize_candidate_key(url)

            if key not in grouped:
                grouped[key] = candidate
            else:
                if candidate["score"] > grouped[key]["score"]:
                    grouped[key] = candidate

        ranked = sorted(grouped.values(), key=lambda x: x["score"], reverse=True)

        self.logger.info(
            f"候选归并完成，归并后数量：{len(grouped)}，最终排序输出数量：{len(ranked)}"
        )

        return [item["url"] for item in ranked]
    
    def extract_image_urls(self, soup: BeautifulSoup, base_url: str):
        dom_candidates = self.extract_candidates_from_dom(soup, base_url)
        final_urls = self.merge_and_rank_candidates(dom_candidates)
        return final_urls