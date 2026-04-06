import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.pipeline import ScrapePipeline
from tests.support.fakes import DummySession, FakeAdapter, FakeRegistry, make_extraction_result


class ScrapePipelineTests(unittest.TestCase):
    def test_resolve_uses_adapter_selected_by_registry(self):
        registry = FakeRegistry()
        pipeline = ScrapePipeline(session=DummySession(), adapter_registry=registry)

        result = pipeline.resolve(
            "https://example.com/gallery",
            mode="dynamic",
            image_urls=["https://cdn.example.com/a.jpg"],
        )

        self.assertEqual(result, ["https://cdn.example.com/a.jpg"])
        self.assertEqual(
            registry.adapter.calls,
            [("https://example.com/gallery", "dynamic", ["https://cdn.example.com/a.jpg"])],
        )
        self.assertEqual(registry.calls[0][0], "https://example.com/gallery")
        self.assertIn("session", registry.calls[0][1])
        self.assertIn("resolver", registry.calls[0][1])

    def test_resolve_result_returns_adapter_result_without_rewriting_it(self):
        adapter = FakeAdapter()
        adapter.next_result = make_extraction_result(
            urls=["https://cdn.example.com/full.jpg"],
            primary_urls=["https://cdn.example.com/full.jpg"],
            source="fake",
            used_browser=True,
        )
        registry = FakeRegistry(adapter=adapter)
        pipeline = ScrapePipeline(session=DummySession(), adapter_registry=registry)

        result = pipeline.resolve_result("https://example.com/gallery")

        self.assertEqual(result.image_urls, ["https://cdn.example.com/full.jpg"])
        self.assertTrue(result.used_browser)
        self.assertEqual(result.primary_image_urls, ["https://cdn.example.com/full.jpg"])


if __name__ == "__main__":
    unittest.main()
