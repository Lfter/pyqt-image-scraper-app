import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.original_resolver import OriginalImageResolver


class OriginalImageResolverTests(unittest.TestCase):
    def setUp(self):
        self.resolver = OriginalImageResolver()

    def test_merge_candidates_prefers_higher_scored_original_variant(self):
        preview = self.resolver.make_candidate(
            "https://cdn.example.com/uploads/photo.jpg~tplv-thumb.avif?sign=small",
            score=50,
            source="payload",
        )
        original = self.resolver.make_candidate(
            "https://cdn.example.com/uploads/photo.jpg~tplv-image.jpg?sign=origin",
            score=500,
            source="payload",
            is_primary=True,
        )

        merged = self.resolver.merge_candidates([preview], [original])

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].url, original.url)
        self.assertTrue(merged[0].is_primary)

    def test_build_image_identity_ignores_resize_and_signature_noise(self):
        first = self.resolver.build_image_identity(
            "https://cdn.example.com/gallery/photo.jpg?width=320&height=180&sign=abc"
        )
        second = self.resolver.build_image_identity(
            "https://cdn.example.com/gallery/photo.jpg?width=2048&height=1536&sign=xyz"
        )

        self.assertEqual(first, second)

    def test_contains_transformed_variants_flags_thumbnail_heavy_collections(self):
        self.assertTrue(
            self.resolver.contains_transformed_variants(
                [
                    "https://cdn.example.com/a.jpg~tplv-thumb.avif",
                    "https://cdn.example.com/b.jpg~tplv-thumb.avif",
                    "https://cdn.example.com/c.jpg",
                ]
            )
        )
        self.assertFalse(
            self.resolver.contains_transformed_variants(
                [
                    "https://cdn.example.com/a.jpg",
                    "https://cdn.example.com/b.jpg",
                ]
            )
        )


if __name__ == "__main__":
    unittest.main()
