import sys
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.extractor import ImageExtractor


class ImageExtractorTests(unittest.TestCase):
    def setUp(self):
        self.extractor = ImageExtractor(session=None)

    def test_extract_image_urls_collects_multiple_sources_and_filters_noise(self):
        soup = BeautifulSoup(
            """
            <html>
                <body>
                    <img src="/images/photo.jpg">
                    <img data-src="//cdn.example.com/banner.webp">
                    <img srcset="/small.jpg 1x, /large.jpg 2x">
                    <a href="/downloads/picture.png">download</a>
                    <div style="background-image: url('/bg.jpeg');"></div>
                    <meta property="og:image" content="/hero.avif">
                    <link rel="preload image" href="/cover.webp">
                    <img src="/assets/logo.png">
                    <link rel="icon" href="/favicon.ico">
                    <img src="data:image/png;base64,abc">
                </body>
            </html>
            """,
            "html.parser",
        )

        image_urls = self.extractor.extract_image_urls(soup, "https://example.com/articles/page.html")

        self.assertEqual(
            image_urls,
            [
                "https://example.com/images/photo.jpg",
                "https://cdn.example.com/banner.webp",
                "https://example.com/large.jpg",
                "https://example.com/downloads/picture.png",
                "https://example.com/bg.jpeg",
                "https://example.com/hero.avif",
                "https://example.com/cover.webp",
            ],
        )

    def test_parse_srcset_prefers_highest_resolution_candidate(self):
        result = self.extractor.parse_srcset("/small.jpg 400w, /medium.jpg 800w, /large.jpg 1200w")
        self.assertEqual(result, ["/large.jpg"])

    def test_normalize_image_url_rejects_non_http_urls(self):
        for raw_url in ("javascript:void(0)", "#gallery", "data:image/png;base64,abc", "about:blank"):
            with self.subTest(raw_url=raw_url):
                self.assertIsNone(
                    self.extractor.normalize_image_url(raw_url, "https://example.com/gallery")
                )


if __name__ == "__main__":
    unittest.main()
