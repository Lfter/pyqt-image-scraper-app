import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.browser.session import BrowserSession


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


class FakePage:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def wait_for_load_state(self, state, timeout=10000):
        self.calls.append((state, timeout))
        if self.error:
            raise self.error


class ClosableObject:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class Stopper:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


class BrowserSessionTests(unittest.TestCase):
    def test_build_authenticated_session_copies_browser_cookies(self):
        session = BrowserSession()
        session.context = FakeContext()

        authenticated = session.build_authenticated_session()

        cookies = {
            (cookie.name, cookie.value, cookie.domain, cookie.path, cookie.secure)
            for cookie in authenticated.cookies
        }
        self.assertIn(("sessionid", "abc123", ".example.com", "/", True), cookies)
        self.assertIn(("auth_token", "secret", "images.example.com", "/private", False), cookies)

    def test_wait_for_network_quietly_ignores_page_errors(self):
        session = BrowserSession()
        session.page = FakePage(error=RuntimeError("network idle unsupported"))

        session.wait_for_network_quietly()

        self.assertEqual(session.page.calls, [("networkidle", 10000)])

    def test_close_resets_browser_references(self):
        session = BrowserSession()
        session.page = ClosableObject()
        session.context = ClosableObject()
        session.browser = ClosableObject()
        session.playwright = Stopper()

        session.close()

        self.assertIsNone(session.page)
        self.assertIsNone(session.context)
        self.assertIsNone(session.browser)
        self.assertIsNone(session.playwright)


if __name__ == "__main__":
    unittest.main()
