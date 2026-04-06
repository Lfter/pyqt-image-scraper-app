import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.adapters.generic import GenericSiteAdapter


class GenericSiteAdapterTests(unittest.TestCase):
    def test_matches_any_url(self):
        self.assertTrue(GenericSiteAdapter.matches("https://example.com/gallery"))
        self.assertTrue(GenericSiteAdapter.matches("https://weibo.com/u/123456"))

    def test_generic_adapter_uses_low_priority_fallback_slot(self):
        self.assertLess(GenericSiteAdapter.priority, 0)


if __name__ == "__main__":
    unittest.main()
