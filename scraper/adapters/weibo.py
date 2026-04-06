from urllib.parse import urlparse, urlunparse

from scraper.adapters.base import BaseSiteAdapter
from scraper.models import ExtractionResult, ImageCandidate


class WeiboSiteAdapter(BaseSiteAdapter):
    name = "weibo"
    priority = 500

    WEIBO_HOST_SUFFIXES = (
        "weibo.com",
        "weibo.cn",
    )
    SINAIMG_HOST_MARKER = "sinaimg.cn"
    LOW_QUALITY_VARIANTS = frozenset(
        {
            "thumbnail",
            "thumb150",
            "square",
            "small",
            "bmiddle",
            "orj360",
            "orj480",
            "mw690",
            "mw1024",
            "mw2000",
        }
    )
    HIGH_QUALITY_VARIANTS = frozenset({"large"})
    CANONICAL_VARIANT = "large"
    VARIANT_SCORE_BONUS = {
        "thumbnail": -120,
        "thumb150": -120,
        "square": -100,
        "small": -90,
        "bmiddle": -80,
        "orj360": -60,
        "orj480": -40,
        "mw690": -20,
        "mw1024": 10,
        "mw2000": 20,
        "large": 80,
    }

    @classmethod
    def matches(cls, page_url: str) -> bool:
        hostname = urlparse(page_url).netloc.lower()
        return any(
            hostname == suffix or hostname.endswith("." + suffix)
            for suffix in cls.WEIBO_HOST_SUFFIXES
        )

    def should_try_browser_assisted_extraction(
        self,
        page_url: str,
        mode: str,
        result: ExtractionResult,
    ) -> bool:
        if mode != "static":
            return False

        if not result.image_urls:
            return True

        if any(self.is_low_quality_weibo_image_url(url) for url in result.image_urls):
            return True

        return super().should_try_browser_assisted_extraction(page_url, mode, result)

    def prepare_result(self, result: ExtractionResult):
        upgraded_primary = self.resolver.merge_candidates(
            self.upgrade_candidate(candidate)
            for candidate in result.primary_candidates
        )
        upgraded_candidates = self.resolver.merge_candidates(
            upgraded_primary,
            (self.upgrade_candidate(candidate) for candidate in result.candidates),
        )
        return ExtractionResult(
            candidates=upgraded_candidates,
            primary_candidates=upgraded_primary,
            used_browser=result.used_browser,
            metadata=dict(result.metadata),
        )

    def upgrade_candidate(self, candidate: ImageCandidate):
        upgraded_url = self.canonicalize_weibo_image_url(candidate.url)
        variant_bonus = self.score_weibo_variant(upgraded_url)
        return ImageCandidate(
            url=upgraded_url,
            identity=self.resolver.build_image_identity(upgraded_url),
            score=candidate.score + variant_bonus,
            source=candidate.source,
            context=candidate.context,
            is_primary=candidate.is_primary,
            metadata=dict(candidate.metadata),
        )

    def canonicalize_weibo_image_url(self, image_url: str) -> str:
        parsed = urlparse(image_url)
        if self.SINAIMG_HOST_MARKER not in parsed.netloc.lower():
            return image_url

        path_parts = parsed.path.split("/")
        if len(path_parts) < 3:
            return image_url

        variant = path_parts[1].lower()
        if variant not in self.LOW_QUALITY_VARIANTS.union(self.HIGH_QUALITY_VARIANTS):
            return image_url

        if variant != self.CANONICAL_VARIANT:
            path_parts[1] = self.CANONICAL_VARIANT

        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                "/".join(path_parts),
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )

    def is_low_quality_weibo_image_url(self, image_url: str) -> bool:
        parsed = urlparse(image_url)
        if self.SINAIMG_HOST_MARKER not in parsed.netloc.lower():
            return False

        path_parts = parsed.path.split("/")
        if len(path_parts) < 3:
            return False

        return path_parts[1].lower() in self.LOW_QUALITY_VARIANTS

    def score_weibo_variant(self, image_url: str) -> int:
        parsed = urlparse(image_url)
        if self.SINAIMG_HOST_MARKER not in parsed.netloc.lower():
            return 0

        path_parts = parsed.path.split("/")
        if len(path_parts) < 3:
            return 0

        return self.VARIANT_SCORE_BONUS.get(path_parts[1].lower(), 0)
