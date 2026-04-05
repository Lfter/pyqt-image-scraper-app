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


if __name__ == "__main__":
    unittest.main()
