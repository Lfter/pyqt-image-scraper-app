import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.adapters.weibo import WeiboSiteAdapter
from tests.support.fakes import DummySession, FakeBrowserExtractor, make_extraction_result, make_static_extractor


class WeiboSiteAdapterTests(unittest.TestCase):
    def test_matches_supported_weibo_hosts(self):
        self.assertTrue(WeiboSiteAdapter.matches("https://weibo.com/1234567890/AbCdEfGhI"))
        self.assertTrue(WeiboSiteAdapter.matches("https://m.weibo.cn/status/1234567890"))
        self.assertTrue(WeiboSiteAdapter.matches("https://weibo.cn/status/1234567890"))
        self.assertFalse(WeiboSiteAdapter.matches("https://example.com/gallery"))

    def test_prepare_result_upgrades_known_sinaimg_variants_to_large(self):
        adapter = WeiboSiteAdapter(session=DummySession())
        result = adapter.extract(
            "https://weibo.com/1234567890/AbCdEfGhI",
            image_urls=[
                "https://wx1.sinaimg.cn/orj360/abc123ly1hxyz.jpg",
                "https://wx1.sinaimg.cn/thumbnail/abc123ly1hxyz.jpg",
                "https://wx2.sinaimg.cn/mw690/def456ly1hxyz.png",
            ],
        )

        self.assertEqual(
            result.image_urls,
            [
                "https://wx1.sinaimg.cn/large/abc123ly1hxyz.jpg",
                "https://wx2.sinaimg.cn/large/def456ly1hxyz.png",
            ],
        )

    def test_static_extract_uses_browser_when_only_low_quality_weibo_variants_exist(self):
        browser_instances = []

        def create_browser_extractor():
            extractor = FakeBrowserExtractor(
                result=make_extraction_result(
                    urls=["https://wx1.sinaimg.cn/large/abc123ly1hxyz.jpg"],
                    primary_urls=["https://wx1.sinaimg.cn/large/abc123ly1hxyz.jpg"],
                    source="fake:weibo",
                    used_browser=True,
                )
            )
            browser_instances.append(extractor)
            return extractor

        statuses = []
        adapter = WeiboSiteAdapter(
            session=DummySession(),
            extractor_factory=make_static_extractor(
                ["https://wx1.sinaimg.cn/orj360/abc123ly1hxyz.jpg"]
            ),
            browser_extractor_factory=create_browser_extractor,
            status_callback=statuses.append,
        )

        result = adapter.extract("https://weibo.com/1234567890/AbCdEfGhI")

        self.assertEqual(
            statuses,
            ["正在获取网页内容...", "正在尝试浏览器辅助提取原图链接..."],
        )
        self.assertEqual(
            result.image_urls,
            ["https://wx1.sinaimg.cn/large/abc123ly1hxyz.jpg"],
        )
        self.assertEqual(
            browser_instances[0].opened,
            [("https://weibo.com/1234567890/AbCdEfGhI", True)],
        )
        self.assertTrue(browser_instances[0].closed)
