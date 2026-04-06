from bs4 import BeautifulSoup

from scraper.browser.expander import PageExpander
from scraper.browser.network_collector import NetworkImageCollector
from scraper.browser.session import BrowserSession
from scraper.extractor import ImageExtractor
from scraper.models import ExtractionResult
from utils.helpers import USER_AGENT


class DynamicImageExtractor(ImageExtractor):
    MAX_AUTO_LOAD_ROUNDS = PageExpander.MAX_AUTO_LOAD_ROUNDS
    STABLE_ROUNDS_TO_STOP = PageExpander.STABLE_ROUNDS_TO_STOP
    SCROLL_PULSES_PER_ROUND = PageExpander.SCROLL_PULSES_PER_ROUND
    SCROLL_PULSE_SETTLE_MS = PageExpander.SCROLL_PULSE_SETTLE_MS
    POST_ACTION_SETTLE_MS = PageExpander.POST_ACTION_SETTLE_MS

    def __init__(self, resolver=None):
        super().__init__(session=None, resolver=resolver)
        self.browser_session = BrowserSession(user_agent=USER_AGENT)
        self.page_expander = PageExpander()
        self.network_collector = NetworkImageCollector(self, resolver=self.resolver)

    @property
    def playwright(self):
        return self.browser_session.playwright

    @playwright.setter
    def playwright(self, value):
        self.browser_session.playwright = value

    @property
    def browser(self):
        return self.browser_session.browser

    @browser.setter
    def browser(self, value):
        self.browser_session.browser = value

    @property
    def context(self):
        return self.browser_session.context

    @context.setter
    def context(self, value):
        self.browser_session.context = value

    @property
    def page(self):
        return self.browser_session.page

    @page.setter
    def page(self, value):
        self.browser_session.page = value

    @property
    def primary_network_candidates(self):
        return self.network_collector.primary_network_candidates

    @primary_network_candidates.setter
    def primary_network_candidates(self, value):
        self.network_collector.primary_network_candidates = list(value)

    @property
    def network_candidates(self):
        return self.network_collector.network_candidates

    @network_candidates.setter
    def network_candidates(self, value):
        self.network_collector.network_candidates = list(value)

    @property
    def primary_network_image_urls(self):
        return self.network_collector.primary_network_image_urls

    @primary_network_image_urls.setter
    def primary_network_image_urls(self, value):
        self.network_collector.primary_network_image_urls = list(value)

    @property
    def network_image_urls(self):
        return self.network_collector.network_image_urls

    @network_image_urls.setter
    def network_image_urls(self, value):
        self.network_collector.network_image_urls = list(value)

    def open_page(self, page_url: str, headless: bool = False):
        self.network_collector.reset()
        self.browser_session.open_page(
            page_url,
            headless=headless,
            response_handler=self.capture_response,
        )

    def extract_result_from_current_page(self, base_url: str):
        if self.page is None:
            raise ValueError("动态页面尚未打开，请先打开页面并完成登录。")

        self.expand_loaded_content()
        self.wait_for_network_quietly()
        html = self.page.content()
        soup = BeautifulSoup(html, "html.parser")
        dom_candidates = self.extract_image_candidates(soup, base_url, source="dom")
        if self.primary_network_candidates:
            return ExtractionResult(
                candidates=list(self.primary_network_candidates),
                primary_candidates=list(self.primary_network_candidates),
                used_browser=True,
            )

        merged_candidates = self.merge_candidate_collections(self.network_candidates, dom_candidates)
        return ExtractionResult(
            candidates=merged_candidates,
            primary_candidates=list(self.primary_network_candidates),
            used_browser=True,
        )

    def extract_from_current_page(self, base_url: str):
        return self.extract_result_from_current_page(base_url).image_urls

    def merge_image_urls(self, primary_urls, fallback_urls):
        candidates = self.merge_candidate_collections(
            self.resolver.candidates_from_urls(primary_urls, source="dynamic"),
            self.resolver.candidates_from_urls(fallback_urls, source="dynamic"),
        )
        return [candidate.url for candidate in candidates]

    def merge_candidate_collections(self, primary_candidates, fallback_candidates):
        return self.resolver.merge_candidates(primary_candidates, fallback_candidates)

    def wait_for_network_quietly(self):
        self.browser_session.wait_for_network_quietly()

    def expand_loaded_content(self):
        self.page_expander.expand(
            page=self.page,
            get_loaded_counts=self.get_loaded_image_counts,
            wait_for_network=self.wait_for_network_quietly,
            scroll_action=self.scroll_loading_surfaces,
            click_action=self.click_load_more_control,
        )

    def get_loaded_image_counts(self):
        return len(self.primary_network_candidates), len(self.network_candidates)

    def scroll_loading_surfaces(self) -> bool:
        return self.page_expander.scroll_loading_surfaces(self.page)

    def click_load_more_control(self) -> bool:
        return self.page_expander.click_load_more_control(self.page)

    def capture_response(self, response):
        self.network_collector.capture_response(response)

    def parse_response_payload(self, response):
        return self.network_collector.parse_response_payload(response)

    def get_response_content_type(self, response):
        return self.network_collector.get_response_content_type(response)

    def get_response_resource_type(self, response):
        return self.network_collector.get_response_resource_type(response)

    def get_response_text(self, response):
        return self.network_collector.get_response_text(response)

    def is_primary_image_payload(self, response_url: str, payload) -> bool:
        return self.network_collector.is_primary_image_payload(response_url, payload)

    def payload_contains_priority_fields(self, payload) -> bool:
        return self.network_collector.payload_contains_priority_fields(payload)

    def build_authenticated_session(self):
        return self.browser_session.build_authenticated_session()

    def sync_network_candidate_urls(self):
        self.network_collector.sync_urls()

    def close(self):
        self.browser_session.close()
