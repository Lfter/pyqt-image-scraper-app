import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.dynamic_extractor import DynamicImageExtractor


class FakeContext:
    def cookies(self):
        return [
            {
                "name": "sessionid",
                "value": "abc123",
                "domain": ".example.com",
                "path": "/",
                "secure": True,
            }
        ]


class FakePage:
    def __init__(self, html="<html></html>"):
        self.html = html

    def content(self):
        return self.html


class FakeExpander:
    def __init__(self):
        self.calls = []
        self.scroll_calls = []
        self.click_calls = []

    def expand(self, **kwargs):
        self.calls.append(kwargs)

    def scroll_loading_surfaces(self, page):
        self.scroll_calls.append(page)
        return False

    def click_load_more_control(self, page):
        self.click_calls.append(page)
        return False


class FakeCollector:
    def __init__(self):
        self.calls = []

    def capture_response(self, response):
        self.calls.append(response)


class DynamicImageExtractorTests(unittest.TestCase):
    def test_build_authenticated_session_uses_browser_session_context(self):
        extractor = DynamicImageExtractor()
        extractor.context = FakeContext()

        session = extractor.build_authenticated_session()

        cookies = {
            (cookie.name, cookie.value, cookie.domain, cookie.path, cookie.secure)
            for cookie in session.cookies
        }
        self.assertIn(("sessionid", "abc123", ".example.com", "/", True), cookies)

    def test_extract_from_current_page_expands_before_returning_primary_urls(self):
        extractor = DynamicImageExtractor()
        extractor.page = FakePage()

        expand_calls = []

        def expand_loaded_content():
            expand_calls.append(True)
            extractor.primary_network_candidates = extractor.resolver.candidates_from_urls(
                ["https://cdn.example.com/full.jpg"],
                source="payload",
                is_primary=True,
            )
            extractor.sync_network_candidate_urls()

        extractor.expand_loaded_content = expand_loaded_content
        extractor.wait_for_network_quietly = lambda: None

        image_urls = extractor.extract_from_current_page("https://example.com/gallery")

        self.assertEqual(expand_calls, [True])
        self.assertEqual(image_urls, ["https://cdn.example.com/full.jpg"])

    def test_expand_loaded_content_delegates_to_page_expander(self):
        extractor = DynamicImageExtractor()
        extractor.page = FakePage()
        extractor.page_expander = FakeExpander()

        extractor.expand_loaded_content()

        self.assertEqual(len(extractor.page_expander.calls), 1)
        call = extractor.page_expander.calls[0]
        self.assertIs(call["page"], extractor.page)
        self.assertEqual(call["get_loaded_counts"](), (0, 0))
        self.assertTrue(call["scroll_action"]() is False)
        self.assertTrue(call["click_action"]() is False)

    def test_capture_response_delegates_to_network_collector(self):
        extractor = DynamicImageExtractor()
        extractor.network_collector = FakeCollector()
        response = object()

        extractor.capture_response(response)

        self.assertEqual(extractor.network_collector.calls, [response])


if __name__ == "__main__":
    unittest.main()
