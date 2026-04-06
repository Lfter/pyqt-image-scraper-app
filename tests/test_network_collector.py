import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.browser.network_collector import NetworkImageCollector
from scraper.extractor import ImageExtractor


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


class NetworkImageCollectorTests(unittest.TestCase):
    def setUp(self):
        self.extractor = ImageExtractor(session=None)
        self.collector = NetworkImageCollector(self.extractor)

    def test_capture_response_prefers_origin_urls_from_json_payload(self):
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

        self.collector.capture_response(response)

        self.assertEqual(
            self.collector.network_image_urls,
            ["https://cdn.example.com/uploads/photo.JPG~tplv-image.JPG?sign=origin"],
        )
        self.assertEqual(
            self.collector.primary_network_image_urls,
            ["https://cdn.example.com/uploads/photo.JPG~tplv-image.JPG?sign=origin"],
        )

    def test_primary_network_payload_wins_over_auxiliary_payloads(self):
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

        self.collector.capture_response(guest_response)
        self.collector.capture_response(photo_response)

        self.assertEqual(
            self.collector.primary_network_image_urls,
            ["https://cdn.example.com/uploads/photo.JPG~tplv-image.JPG?sign=origin"],
        )
        self.assertEqual(
            self.collector.network_image_urls,
            ["https://cdn.example.com/uploads/photo.JPG~tplv-image.JPG?sign=origin"],
        )


if __name__ == "__main__":
    unittest.main()
