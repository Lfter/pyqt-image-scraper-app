from scraper.extractor import ImageExtractor
from scraper.models import ExtractionResult
from scraper.original_resolver import OriginalImageResolver


class BaseSiteAdapter:
    name = "base"
    priority = 0

    @classmethod
    def matches(cls, page_url: str) -> bool:
        del page_url
        return False

    def __init__(
        self,
        session,
        extractor_factory=ImageExtractor,
        browser_extractor_factory=None,
        resolver=None,
        status_callback=None,
    ):
        self.session = session
        self.extractor_factory = extractor_factory
        self.browser_extractor_factory = browser_extractor_factory
        self.resolver = resolver or OriginalImageResolver()
        self.status_callback = status_callback

    def emit_status(self, message: str):
        if self.status_callback:
            self.status_callback(message)

    def prepare_result(self, result: ExtractionResult):
        return result

    def extract(self, page_url: str, mode: str = "static", image_urls=None):
        if image_urls is not None:
            self.emit_status("正在整理图片链接...")
            return self.prepare_result(
                self.resolver.result_from_urls(image_urls, source=f"{self.name}:provided")
            )

        if mode == "dynamic":
            return self.extract_dynamic(page_url)

        self.emit_status("正在获取网页内容...")
        result = self.extract_static(page_url)

        if self.should_try_browser_assisted_extraction(page_url, mode, result):
            return self.extract_with_browser(page_url, result)

        return self.prepare_result(result)

    def extract_dynamic(self, page_url: str):
        empty_result = ExtractionResult(candidates=[])
        return self.extract_with_browser(page_url, empty_result)

    def extract_static(self, page_url: str):
        extractor = self.extractor_factory(self.session)

        if hasattr(extractor, "extract_result_from_page"):
            return extractor.extract_result_from_page(page_url)

        return self.resolver.result_from_urls(
            extractor.extract_from_page(page_url),
            source=f"{self.name}:static",
        )

    def should_try_browser_assisted_extraction(
        self,
        page_url: str,
        mode: str,
        result: ExtractionResult,
    ) -> bool:
        del page_url
        return mode == "static" and self.resolver.contains_transformed_variants(result.image_urls)

    def extract_with_browser(self, page_url: str, fallback_result: ExtractionResult):
        try:
            browser_extractor = self.create_browser_extractor()
        except Exception:
            return self.prepare_result(fallback_result)

        self.emit_status("正在尝试浏览器辅助提取原图链接...")

        try:
            browser_extractor.open_page(page_url, headless=True)
            browser_result = self.extract_with_browser_extractor(browser_extractor, page_url)
            self.merge_authenticated_session(browser_extractor.build_authenticated_session())
            return self.prepare_result(self.merge_results(browser_result, fallback_result))
        except Exception:
            return self.prepare_result(fallback_result)
        finally:
            browser_extractor.close()

    def create_browser_extractor(self):
        if self.browser_extractor_factory is not None:
            return self.browser_extractor_factory()

        from scraper.dynamic_extractor import DynamicImageExtractor

        return DynamicImageExtractor()

    def extract_with_browser_extractor(self, browser_extractor, page_url: str):
        if hasattr(browser_extractor, "extract_result_from_current_page"):
            result = browser_extractor.extract_result_from_current_page(page_url)
        else:
            image_urls = browser_extractor.extract_from_current_page(page_url)
            primary_urls = getattr(browser_extractor, "primary_network_image_urls", None) or []
            primary_candidates = self.resolver.candidates_from_urls(
                primary_urls,
                source=f"{self.name}:network",
                is_primary=True,
            )
            candidates = self.resolver.merge_candidates(
                primary_candidates,
                self.resolver.candidates_from_urls(image_urls, source=f"{self.name}:browser"),
            )
            result = ExtractionResult(
                candidates=candidates,
                primary_candidates=primary_candidates,
                used_browser=True,
            )

        return ExtractionResult(
            candidates=self.resolver.merge_candidates(result.candidates),
            primary_candidates=self.resolver.merge_candidates(result.primary_candidates),
            used_browser=True,
            metadata=dict(result.metadata),
        )

    def merge_results(self, browser_result: ExtractionResult, fallback_result: ExtractionResult):
        if browser_result.primary_candidates:
            return browser_result

        merged_candidates = self.resolver.merge_candidates(
            browser_result.candidates,
            fallback_result.candidates,
        )
        return ExtractionResult(
            candidates=merged_candidates,
            primary_candidates=browser_result.primary_candidates,
            used_browser=browser_result.used_browser,
            metadata=dict(browser_result.metadata),
        )

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
