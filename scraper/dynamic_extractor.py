import json
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from scraper.extractor import ImageExtractor
from utils.helpers import USER_AGENT


class DynamicImageExtractor(ImageExtractor):
    MAX_AUTO_LOAD_ROUNDS = 24
    STABLE_ROUNDS_TO_STOP = 3
    SCROLL_PULSES_PER_ROUND = 4
    SCROLL_PULSE_SETTLE_MS = 250
    POST_ACTION_SETTLE_MS = 700

    def __init__(self):
        super().__init__(session=None)
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.primary_network_image_urls = []
        self.network_image_urls = []

    def open_page(self, page_url: str, headless: bool = False):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=headless)
        self.context = self.browser.new_context(user_agent=USER_AGENT)
        self.page = self.context.new_page()
        self.primary_network_image_urls = []
        self.network_image_urls = []
        self.page.on("response", self.capture_response)
        self.page.goto(page_url, wait_until="domcontentloaded", timeout=120000)
        self.wait_for_network_quietly()

    def extract_from_current_page(self, base_url: str):
        if self.page is None:
            raise ValueError("动态页面尚未打开，请先打开页面并完成登录。")

        self.expand_loaded_content()
        self.wait_for_network_quietly()
        html = self.page.content()
        soup = BeautifulSoup(html, "html.parser")
        dom_urls = self.extract_image_urls(soup, base_url)
        if self.primary_network_image_urls:
            return list(self.primary_network_image_urls)
        return self.merge_image_urls(self.network_image_urls, dom_urls)

    def merge_image_urls(self, primary_urls, fallback_urls):
        merged = []
        seen = set()

        for collection in (primary_urls, fallback_urls):
            for item in collection:
                normalized = self.normalize_image_url(item, "")
                if not normalized:
                    normalized = item
                identity = self.build_image_identity(normalized)
                if identity in seen:
                    continue
                seen.add(identity)
                merged.append(normalized)

        return merged

    def wait_for_network_quietly(self):
        if self.page is None:
            return
        try:
            self.page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

    def expand_loaded_content(self):
        if self.page is None:
            return

        stable_rounds = 0
        last_counts = self.get_loaded_image_counts()

        for _ in range(self.MAX_AUTO_LOAD_ROUNDS):
            moved = self.scroll_loading_surfaces()
            clicked = self.click_load_more_control()

            if moved or clicked:
                self.wait_for_network_quietly()
                self.page.wait_for_timeout(self.POST_ACTION_SETTLE_MS)
                self.wait_for_network_quietly()

            current_counts = self.get_loaded_image_counts()
            if current_counts != last_counts:
                last_counts = current_counts
                stable_rounds = 0
                continue

            if moved or clicked:
                last_counts = current_counts
                stable_rounds = 0
                continue

            stable_rounds += 1
            if stable_rounds >= self.STABLE_ROUNDS_TO_STOP:
                break

            self.page.wait_for_timeout(self.POST_ACTION_SETTLE_MS)

    def get_loaded_image_counts(self):
        return len(self.primary_network_image_urls), len(self.network_image_urls)

    def scroll_loading_surfaces(self) -> bool:
        if self.page is None:
            return False

        moved_any = False
        for _ in range(self.SCROLL_PULSES_PER_ROUND):
            try:
                result = self.page.evaluate(
                    """() => {
                        const clampMax = (value) => Math.max(0, value || 0);
                        const maxWindowY = clampMax(
                            Math.max(
                                document.documentElement ? document.documentElement.scrollHeight - window.innerHeight : 0,
                                document.body ? document.body.scrollHeight - window.innerHeight : 0,
                            )
                        );
                        const beforeWindowY = window.scrollY || window.pageYOffset || 0;
                        window.scrollTo(0, maxWindowY);
                        let moved = Math.abs((window.scrollY || window.pageYOffset || 0) - beforeWindowY) > 1;

                        const scrollables = Array.from(document.querySelectorAll('*'))
                            .filter((el) => {
                                const style = window.getComputedStyle(el);
                                const overflowY = (style.overflowY || '').toLowerCase();
                                const overflow = (style.overflow || '').toLowerCase();
                                const rect = el.getBoundingClientRect();
                                const scrollable =
                                    ['auto', 'scroll', 'overlay'].includes(overflowY) ||
                                    ['auto', 'scroll', 'overlay'].includes(overflow);
                                return (
                                    scrollable &&
                                    rect.width > 0 &&
                                    rect.height > 0 &&
                                    el.clientHeight > 0 &&
                                    el.scrollHeight > el.clientHeight + 200
                                );
                            })
                            .sort((left, right) => {
                                const leftDelta = left.scrollHeight - left.clientHeight;
                                const rightDelta = right.scrollHeight - right.clientHeight;
                                return rightDelta - leftDelta;
                            })
                            .slice(0, 8);

                        for (const el of scrollables) {
                            const maxTop = clampMax(el.scrollHeight - el.clientHeight);
                            const beforeTop = el.scrollTop || 0;
                            const delta = Math.max(el.clientHeight * 1.5, 900);
                            const targetTop = Math.min(beforeTop + delta, maxTop);
                            if (Math.abs(targetTop - beforeTop) <= 1) {
                                continue;
                            }

                            el.scrollTop = targetTop;
                            el.dispatchEvent(new Event('scroll', { bubbles: true }));
                            el.dispatchEvent(new WheelEvent('wheel', { deltaY: targetTop - beforeTop, bubbles: true }));

                            if (Math.abs((el.scrollTop || 0) - beforeTop) > 1) {
                                moved = true;
                            }
                        }

                        return { moved };
                    }"""
                )
            except Exception:
                return moved_any
            moved = bool(result and result.get("moved"))
            moved_any = moved_any or moved
            if not moved:
                break
            self.page.wait_for_timeout(self.SCROLL_PULSE_SETTLE_MS)

        return moved_any

    def click_load_more_control(self) -> bool:
        if self.page is None:
            return False

        try:
            result = self.page.evaluate(
                """() => {
                    const positivePattern = /(load\\s*more|show\\s*more|view\\s*more|more\\s*(photos|images|pictures|results)?|next\\s*page|pagination\\s*next|下一页|下页|更多|加载更多|继续加载|查看更多|展开更多)/i;
                    const negativePattern = /(prev|previous|上一页|上页|login|登录|注册|download|下载|share|分享|close|关闭|cancel|取消)/i;
                    const paginationHintPattern = /(next|page|pager|pagination|gallery|album|photo|image|pic|列表|相册|图片|照片|翻页|更多)/i;

                    const isVisible = (el) => {
                        if (!el) {
                            return false;
                        }
                        if (typeof el.checkVisibility === 'function') {
                            try {
                                if (!el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) {
                                    return false;
                                }
                            } catch (error) {
                                void error;
                            }
                        }
                        const rect = el.getBoundingClientRect();
                        if (rect.width <= 0 || rect.height <= 0) {
                            return false;
                        }
                        const style = window.getComputedStyle(el);
                        return style.display !== 'none' && style.visibility !== 'hidden' && style.pointerEvents !== 'none';
                    };

                    const candidates = Array.from(
                        document.querySelectorAll('button, [role="button"], a[href], input[type="button"], input[type="submit"]')
                    )
                        .filter((el) => {
                            const ariaDisabled = (el.getAttribute('aria-disabled') || '').toLowerCase();
                            return isVisible(el) && !el.disabled && ariaDisabled !== 'true';
                        })
                        .map((el) => {
                            const textParts = [
                                el.innerText,
                                el.textContent,
                                el.value,
                                el.getAttribute('aria-label'),
                                el.getAttribute('title'),
                                el.getAttribute('class'),
                                el.getAttribute('id'),
                                el.getAttribute('href'),
                            ]
                                .filter(Boolean)
                                .join(' ')
                                .replace(/\\s+/g, ' ')
                                .trim();
                            const lowerText = textParts.toLowerCase();
                            if (!positivePattern.test(lowerText)) {
                                return null;
                            }
                            if (negativePattern.test(lowerText)) {
                                return null;
                            }

                            let score = 0;
                            if (/(load\\s*more|show\\s*more|view\\s*more|加载更多|继续加载|查看更多|展开更多)/i.test(lowerText)) {
                                score += 5;
                            }
                            if (/(next\\s*page|pagination\\s*next|下一页|下页)/i.test(lowerText)) {
                                score += 4;
                            }
                            if (/(更多|more)/i.test(lowerText)) {
                                score += 2;
                            }
                            if (paginationHintPattern.test(lowerText)) {
                                score += 1;
                            }

                            const rect = el.getBoundingClientRect();
                            return { el, score, top: rect.top, textLength: lowerText.length };
                        })
                        .filter(Boolean)
                        .sort((left, right) => {
                            if (right.score !== left.score) {
                                return right.score - left.score;
                            }
                            if (right.top !== left.top) {
                                return right.top - left.top;
                            }
                            return left.textLength - right.textLength;
                        });

                    const best = candidates[0];
                    if (!best) {
                        return false;
                    }

                    best.el.click();
                    return true;
                }"""
            )
        except Exception:
            return False
        return bool(result)

    def capture_response(self, response):
        payload = self.parse_response_payload(response)
        if payload is None:
            return

        response_url = getattr(response, "url", "") or ""
        extracted_urls = self.extract_image_urls_from_payload(payload, response_url)
        if extracted_urls:
            if self.is_primary_image_payload(response_url, payload):
                self.primary_network_image_urls = self.merge_image_urls(
                    extracted_urls,
                    self.primary_network_image_urls,
                )
                self.network_image_urls = self.merge_image_urls(
                    self.primary_network_image_urls,
                    self.network_image_urls,
                )
            else:
                self.network_image_urls = self.merge_image_urls(extracted_urls, self.network_image_urls)

    def parse_response_payload(self, response):
        content_type = (self.get_response_content_type(response) or "").lower()
        resource_type = self.get_response_resource_type(response)

        if content_type and "json" not in content_type and resource_type not in {"xhr", "fetch"}:
            return None

        text = self.get_response_text(response)
        if not text:
            return None

        if "json" not in content_type and resource_type not in {"xhr", "fetch"}:
            stripped = text.lstrip()
            if not stripped.startswith(("{", "[")):
                return None

        try:
            return json.loads(text)
        except (TypeError, ValueError):
            return None

    def get_response_content_type(self, response):
        header_value = getattr(response, "header_value", None)
        if callable(header_value):
            try:
                content_type = header_value("content-type")
                if content_type:
                    return content_type
            except Exception:
                pass

        headers = getattr(response, "headers", None)
        if callable(headers):
            try:
                headers = headers()
            except Exception:
                headers = None

        if isinstance(headers, dict):
            for key, value in headers.items():
                if str(key).lower() == "content-type":
                    return value

        return ""

    def get_response_resource_type(self, response):
        request = getattr(response, "request", None)
        if request is None:
            return ""

        resource_type = getattr(request, "resource_type", "")
        if callable(resource_type):
            try:
                return resource_type()
            except Exception:
                return ""
        return resource_type or ""

    def get_response_text(self, response):
        text_method = getattr(response, "text", None)
        if callable(text_method):
            try:
                return text_method()
            except Exception:
                return None
        return None

    def is_primary_image_payload(self, response_url: str, payload) -> bool:
        lowered_url = response_url.lower()
        if any(marker in lowered_url for marker in ("/pic/", "/photo/", "/image/", "/gallery/", "/album/")):
            return True
        return self.payload_contains_priority_fields(payload)

    def payload_contains_priority_fields(self, payload) -> bool:
        def walk(node, path_segments=()):
            if isinstance(node, dict):
                for key, value in node.items():
                    if walk(value, path_segments + (str(key).lower(),)):
                        return True
                return False

            if isinstance(node, list):
                return any(walk(item, path_segments) for item in node)

            if not isinstance(node, str):
                return False

            path_text = " ".join(path_segments)
            if not self.looks_like_payload_image_value(node):
                return False

            has_priority_marker = any(
                marker in path_text for marker in ("origin", "original", "master", "raw", "download")
            )
            has_image_marker = any(
                marker in path_text for marker in ("img", "image", "pic", "photo", "cover", "poster")
            )
            return has_priority_marker and has_image_marker

        return walk(payload)

    def build_authenticated_session(self):
        if self.context is None:
            raise ValueError("动态页面尚未打开，无法同步登录状态。")

        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})

        for cookie in self.context.cookies():
            session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie.get("domain"),
                path=cookie.get("path", "/"),
                secure=cookie.get("secure", False),
            )

        return session

    def close(self):
        if self.page:
            self.page.close()
            self.page = None
        if self.context:
            self.context.close()
            self.context = None
        if self.browser:
            self.browser.close()
            self.browser = None
        if self.playwright:
            self.playwright.stop()
            self.playwright = None
