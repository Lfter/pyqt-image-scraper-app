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
            },
            {
                "name": "auth_token",
                "value": "secret",
                "domain": "images.example.com",
                "path": "/private",
                "secure": False,
            },
        ]


class FakeRequest:
    def __init__(self, resource_type):
        self.resource_type = resource_type


class FakeResponse:
    def __init__(self, url, content_type, text, resource_type="xhr"):
        self.url = url
        self._content_type = content_type
        self._text = text
        self.request = FakeRequest(resource_type)

    def header_value(self, name):
        if name.lower() == "content-type":
            return self._content_type
        return None

    def text(self):
        return self._text


class FakePage:
    def __init__(self, html="<html></html>"):
        self.html = html
        self.timeouts = []

    def content(self):
        return self.html

    def wait_for_timeout(self, milliseconds):
        self.timeouts.append(milliseconds)


class DynamicImageExtractorTests(unittest.TestCase):
    def test_build_authenticated_session_copies_browser_cookies(self):
        extractor = DynamicImageExtractor()
        extractor.context = FakeContext()

        session = extractor.build_authenticated_session()

        cookies = {
            (cookie.name, cookie.value, cookie.domain, cookie.path, cookie.secure)
            for cookie in session.cookies
        }
        self.assertIn(("sessionid", "abc123", ".example.com", "/", True), cookies)
        self.assertIn(("auth_token", "secret", "images.example.com", "/private", False), cookies)

    def test_capture_response_prefers_origin_urls_from_json_payload(self):
        extractor = DynamicImageExtractor()
        response = FakeResponse(
            "https://example.com/api/pic/list",
            "application/json",
            """
            {
              "result": {
                "pics_array": [
                  {
                    "small_img": "https://cdn.example.com/uploads/photo.JPG~tplv-thumb.avif?sign=small",
                    "origin_img": "https://cdn.example.com/uploads/photo.JPG~tplv-image.JPG?sign=origin"
                  }
                ]
              }
            }
            """,
        )

        extractor.capture_response(response)

        self.assertEqual(
            extractor.network_image_urls,
            ["https://cdn.example.com/uploads/photo.JPG~tplv-image.JPG?sign=origin"],
        )
        self.assertEqual(
            extractor.primary_network_image_urls,
            ["https://cdn.example.com/uploads/photo.JPG~tplv-image.JPG?sign=origin"],
        )

    def test_primary_network_payload_wins_over_auxiliary_payloads(self):
        extractor = DynamicImageExtractor()
        guest_response = FakeResponse(
            "https://example.com/live/guest/list",
            "application/json",
            """
            {
              "result": {
                "guest_list": [
                  {
                    "big_img": "https://cdn.example.com/guest/avatar.jpg~tplv-image.image?sign=guest"
                  }
                ]
              }
            }
            """,
        )
        photo_response = FakeResponse(
            "https://example.com/pic/list",
            "application/json",
            """
            {
              "result": {
                "pics_array": [
                  {
                    "origin_img": "https://cdn.example.com/uploads/photo.JPG~tplv-image.JPG?sign=origin"
                  }
                ]
              }
            }
            """,
        )

        extractor.capture_response(guest_response)
        extractor.capture_response(photo_response)

        self.assertEqual(
            extractor.primary_network_image_urls,
            ["https://cdn.example.com/uploads/photo.JPG~tplv-image.JPG?sign=origin"],
        )
        self.assertEqual(
            extractor.network_image_urls,
            ["https://cdn.example.com/uploads/photo.JPG~tplv-image.JPG?sign=origin"],
        )

    def test_extract_from_current_page_expands_before_returning_primary_urls(self):
        extractor = DynamicImageExtractor()
        extractor.page = FakePage()

        expand_calls = []

        def expand_loaded_content():
            expand_calls.append(True)
            extractor.primary_network_image_urls = ["https://cdn.example.com/full.jpg"]

        extractor.expand_loaded_content = expand_loaded_content
        extractor.wait_for_network_quietly = lambda: None

        image_urls = extractor.extract_from_current_page("https://example.com/gallery")

        self.assertEqual(expand_calls, [True])
        self.assertEqual(image_urls, ["https://cdn.example.com/full.jpg"])

    def test_expand_loaded_content_keeps_advancing_until_page_stabilizes(self):
        extractor = DynamicImageExtractor()
        extractor.page = FakePage()
        extractor.primary_network_image_urls = [f"https://cdn.example.com/{index}.jpg" for index in range(100)]
        extractor.network_image_urls = [f"https://cdn.example.com/{index}.jpg" for index in range(101)]

        states = [
            {"moved": True, "clicked": False, "counts": (100, 101)},
            {"moved": True, "clicked": False, "counts": (100, 101)},
            {"moved": True, "clicked": False, "counts": (200, 201)},
            {"moved": False, "clicked": False, "counts": (200, 201)},
            {"moved": False, "clicked": False, "counts": (200, 201)},
            {"moved": False, "clicked": False, "counts": (200, 201)},
        ]
        round_index = {"value": 0}
        wait_calls = []

        def advance_round():
            state = states[round_index["value"]]
            primary_count, network_count = state["counts"]
            extractor.primary_network_image_urls = [
                f"https://cdn.example.com/p{index}.jpg" for index in range(primary_count)
            ]
            extractor.network_image_urls = [
                f"https://cdn.example.com/n{index}.jpg" for index in range(network_count)
            ]
            round_index["value"] += 1
            return state["moved"]

        def click_load_more_control():
            return states[round_index["value"] - 1]["clicked"]

        extractor.scroll_loading_surfaces = advance_round
        extractor.click_load_more_control = click_load_more_control
        extractor.wait_for_network_quietly = lambda: wait_calls.append(round_index["value"])

        extractor.expand_loaded_content()

        self.assertEqual(round_index["value"], len(states))
        self.assertEqual(extractor.get_loaded_image_counts(), (200, 201))
        self.assertGreaterEqual(len(wait_calls), 3)
        self.assertEqual(
            extractor.page.timeouts.count(extractor.POST_ACTION_SETTLE_MS),
            5,
        )


if __name__ == "__main__":
    unittest.main()
