import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.support.fakes import (
    DummySession,
    FakeBrowserExtractor,
    make_extraction_result,
    make_static_extractor,
)


class AdapterContractMixin:
    adapter_cls = None
    page_url = "https://example.com/gallery"

    def create_adapter(self, **kwargs):
        if self.adapter_cls is None:
            raise AssertionError("adapter_cls must be set on the contract test case")

        return self.adapter_cls(session=DummySession(), **kwargs)

    def test_contract_deduplicates_provided_urls_and_emits_status(self):
        statuses = []
        adapter = self.create_adapter(status_callback=statuses.append)

        result = adapter.extract(
            self.page_url,
            image_urls=[
                "https://cdn.example.com/a.jpg",
                "https://cdn.example.com/a.jpg",
                "https://cdn.example.com/b.jpg",
            ],
        )

        self.assertEqual(statuses, ["正在整理图片链接..."])
        self.assertEqual(
            result.image_urls,
            ["https://cdn.example.com/a.jpg", "https://cdn.example.com/b.jpg"],
        )

    def test_contract_uses_browser_result_when_transformed_variants_dominate(self):
        browser_instances = []

        def create_browser_extractor():
            extractor = FakeBrowserExtractor(
                urls=["https://cdn.example.com/a.jpg"],
            )
            extractor.authenticated_session.cookies.set(
                "sessionid",
                "abc123",
                domain=".example.com",
                path="/",
                secure=True,
            )
            browser_instances.append(extractor)
            return extractor

        statuses = []
        session = DummySession()
        adapter = self.adapter_cls(
            session=session,
            extractor_factory=make_static_extractor(
                ["https://cdn.example.com/a.jpg~tplv-thumb.avif"]
            ),
            browser_extractor_factory=create_browser_extractor,
            status_callback=statuses.append,
        )

        result = adapter.extract(self.page_url)

        self.assertEqual(
            statuses,
            ["正在获取网页内容...", "正在尝试浏览器辅助提取原图链接..."],
        )
        self.assertEqual(result.image_urls, ["https://cdn.example.com/a.jpg"])
        self.assertEqual(browser_instances[0].opened, [(self.page_url, True)])
        self.assertTrue(browser_instances[0].closed)
        self.assertEqual(
            session.cookies.items,
            [("sessionid", "abc123", ".example.com", "/", True)],
        )

    def test_contract_prefers_browser_primary_results_without_merging_fallbacks(self):
        browser_instances = []

        def create_browser_extractor():
            extractor = FakeBrowserExtractor(
                result=make_extraction_result(
                    urls=["https://cdn.example.com/full.jpg"],
                    primary_urls=["https://cdn.example.com/full.jpg"],
                    source="fake:network",
                    used_browser=True,
                )
            )
            browser_instances.append(extractor)
            return extractor

        adapter = self.create_adapter(
            extractor_factory=make_static_extractor(
                [
                    "https://cdn.example.com/a.jpg~tplv-thumb.avif",
                    "https://example.com/pic/a.jpg",
                ]
            ),
            browser_extractor_factory=create_browser_extractor,
        )

        result = adapter.extract(self.page_url)

        self.assertEqual(result.image_urls, ["https://cdn.example.com/full.jpg"])
        self.assertEqual(
            result.primary_image_urls,
            ["https://cdn.example.com/full.jpg"],
        )
        self.assertTrue(browser_instances[0].closed)

    def test_contract_dynamic_mode_uses_browser_flow(self):
        browser_instances = []

        def create_browser_extractor():
            extractor = FakeBrowserExtractor(
                result=make_extraction_result(
                    urls=["https://cdn.example.com/dynamic.jpg"],
                    primary_urls=["https://cdn.example.com/dynamic.jpg"],
                    source="fake:dynamic",
                    used_browser=True,
                )
            )
            browser_instances.append(extractor)
            return extractor

        statuses = []
        adapter = self.create_adapter(
            browser_extractor_factory=create_browser_extractor,
            status_callback=statuses.append,
        )

        result = adapter.extract(self.page_url, mode="dynamic")

        self.assertEqual(statuses, ["正在尝试浏览器辅助提取原图链接..."])
        self.assertEqual(result.image_urls, ["https://cdn.example.com/dynamic.jpg"])
        self.assertTrue(result.used_browser)
        self.assertEqual(browser_instances[0].opened, [(self.page_url, True)])
        self.assertTrue(browser_instances[0].closed)
