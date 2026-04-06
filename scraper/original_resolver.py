import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from scraper.models import ExtractionResult, ImageCandidate
from utils.helpers import VALID_IMAGE_EXTENSIONS


class OriginalImageResolver:
    TRANSFORMED_URL_MARKERS = (
        "~",
        "resize",
        "thumbnail",
        "thumb",
        "preview",
        "crop",
        "fit=",
        "width=",
        "height=",
        "imagex",
    )
    IMAGE_EXTENSION_PATTERN = "|".join(
        sorted(
            {re.escape(ext.lstrip(".")) for ext in VALID_IMAGE_EXTENSIONS},
            key=len,
            reverse=True,
        )
    )
    RESIZE_QUERY_KEYS = frozenset(
        {
            "w",
            "width",
            "h",
            "height",
            "fit",
            "crop",
            "resize",
            "size",
            "quality",
            "q",
            "dpr",
            "imgmax",
            "maxwidth",
            "maxheight",
        }
    )
    IDENTITY_IGNORED_QUERY_KEYS = RESIZE_QUERY_KEYS.union(
        {
            "sign",
            "signature",
            "token",
            "expires",
            "exp",
            "auth",
            "auth_key",
            "authkey",
            "x-amz-signature",
            "x-amz-credential",
            "x-amz-date",
            "x-amz-expires",
            "x-amz-security-token",
            "x-goog-signature",
            "x-goog-credential",
            "x-goog-date",
            "x-goog-expires",
            "x-goog-security-token",
        }
    )

    def normalize_url(self, raw_url: str, base_url: str):
        if not raw_url:
            return None

        raw_url = raw_url.strip().strip("\"'")
        if raw_url.startswith(("data:", "javascript:", "#", "about:")):
            return None

        if raw_url.startswith("//"):
            raw_url = "https:" + raw_url

        full_url = urljoin(base_url, raw_url)
        parsed = urlparse(full_url)

        if parsed.scheme not in {"http", "https"}:
            return None

        return full_url

    def make_candidate(
        self,
        raw_url: str,
        base_url: str = "",
        *,
        score: int = 0,
        source: str = "unknown",
        context: str = "",
        is_primary: bool = False,
        metadata=None,
    ):
        normalized_url = self.normalize_url(raw_url, base_url)
        if not normalized_url:
            return None

        return ImageCandidate(
            url=normalized_url,
            identity=self.build_image_identity(normalized_url),
            score=score + self.score_image_candidate_url(normalized_url),
            source=source,
            context=context,
            is_primary=is_primary,
            metadata=dict(metadata or {}),
        )

    def is_better_candidate(self, candidate: ImageCandidate, existing: ImageCandidate) -> bool:
        candidate_rank = (candidate.score, 1 if candidate.is_primary else 0)
        existing_rank = (existing.score, 1 if existing.is_primary else 0)
        return candidate_rank > existing_rank

    def merge_candidates(self, *collections):
        ranked_candidates = {}
        ordered_keys = []

        for collection in collections:
            for candidate in collection:
                if candidate is None:
                    continue

                prepared = self.prepare_candidate(candidate)
                existing = ranked_candidates.get(prepared.identity)

                if existing is None:
                    ordered_keys.append(prepared.identity)
                    ranked_candidates[prepared.identity] = prepared
                    continue

                if self.is_better_candidate(prepared, existing):
                    ranked_candidates[prepared.identity] = prepared

        return [ranked_candidates[key] for key in ordered_keys]

    def prepare_candidate(self, candidate: ImageCandidate) -> ImageCandidate:
        if candidate.identity:
            return candidate

        return ImageCandidate(
            url=candidate.url,
            identity=self.build_image_identity(candidate.url),
            score=candidate.score,
            source=candidate.source,
            context=candidate.context,
            is_primary=candidate.is_primary,
            metadata=dict(candidate.metadata),
        )

    def candidates_from_urls(self, image_urls, *, source="unknown", context="", is_primary=False):
        candidates = []

        for image_url in image_urls:
            candidate = self.make_candidate(
                image_url,
                "",
                source=source,
                context=context,
                is_primary=is_primary,
            )
            if candidate is not None:
                candidates.append(candidate)

        return self.merge_candidates(candidates)

    def result_from_urls(self, image_urls, *, source="unknown", context="", is_primary=False):
        candidates = self.candidates_from_urls(
            image_urls,
            source=source,
            context=context,
            is_primary=is_primary,
        )
        primary_candidates = candidates if is_primary else []
        return ExtractionResult(candidates=candidates, primary_candidates=primary_candidates)

    def build_image_identity(self, image_url: str) -> str:
        parsed = urlparse(image_url)
        normalized_path = self.strip_resize_suffix(
            self.strip_post_extension_transform_suffix(parsed.path)
        )
        filtered_query = self.filter_identity_query(parsed.query)
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                normalized_path,
                parsed.params,
                filtered_query,
                "",
            )
        )

    def strip_resize_suffix(self, path: str) -> str:
        return re.sub(r"([_-])\d{2,5}x\d{2,5}(?=\.[a-z0-9]+$)", "", path, flags=re.IGNORECASE)

    def strip_post_extension_transform_suffix(self, path: str) -> str:
        pattern = rf"(\.(?:{self.IMAGE_EXTENSION_PATTERN}))(?:[~!@].+)$"
        return re.sub(pattern, r"\1", path, flags=re.IGNORECASE)

    def filter_resize_query(self, query: str) -> str:
        if not query:
            return ""

        filtered_pairs = [
            (key, value)
            for key, value in parse_qsl(query, keep_blank_values=True)
            if key.lower() not in self.RESIZE_QUERY_KEYS
        ]
        return urlencode(filtered_pairs, doseq=True)

    def filter_identity_query(self, query: str) -> str:
        if not query:
            return ""

        filtered_pairs = [
            (key, value)
            for key, value in parse_qsl(query, keep_blank_values=True)
            if key.lower() not in self.IDENTITY_IGNORED_QUERY_KEYS
        ]
        return urlencode(filtered_pairs, doseq=True)

    def score_image_candidate_url(self, image_url: str) -> int:
        parsed = urlparse(image_url)
        path_bonus = self.extract_size_score_from_path(parsed.path)
        query_bonus = self.extract_size_score_from_query(parsed.query)
        return min(max(path_bonus, query_bonus) // 10, 180)

    def extract_size_score_from_path(self, path: str) -> int:
        path = self.strip_post_extension_transform_suffix(path)
        match = re.search(r"(\d{2,5})x(\d{2,5})(?=\.[a-z0-9]+$)", path, flags=re.IGNORECASE)
        if not match:
            return 0
        return max(int(match.group(1)), int(match.group(2)))

    def extract_size_score_from_query(self, query: str) -> int:
        size_values = []
        for key, value in parse_qsl(query, keep_blank_values=True):
            if key.lower() in {"w", "width", "h", "height"} and value.isdigit():
                size_values.append(int(value))
        return max(size_values, default=0)

    def looks_like_image(self, url: str) -> bool:
        path = urlparse(url).path.lower()
        if any(path.endswith(ext) for ext in VALID_IMAGE_EXTENSIONS):
            return True

        stripped_path = self.strip_post_extension_transform_suffix(path)
        return any(stripped_path.endswith(ext) for ext in VALID_IMAGE_EXTENSIONS)

    def is_transformed_image_url(self, image_url: str) -> bool:
        lowered = image_url.lower()
        return any(marker in lowered for marker in self.TRANSFORMED_URL_MARKERS)

    def contains_transformed_variants(self, image_urls) -> bool:
        if not image_urls:
            return True

        transformed_count = sum(1 for item in image_urls if self.is_transformed_image_url(item))
        return transformed_count >= max(1, len(image_urls) // 2)

    def should_prefer_original_url(self, image_url: str) -> bool:
        path = urlparse(image_url).path.lower()
        if "~" not in path:
            return False

        if any(
            marker in path
            for marker in ("resize", "thumb", "thumbnail", "preview", "crop", "small_", "middle_")
        ):
            return False

        return any(marker in path for marker in ("-image.", "origin", "original", "master", "raw"))

    def strip_resize_suffix_from_url(self, image_url: str) -> str:
        parsed = urlparse(image_url)
        stripped_path = self.strip_resize_suffix(parsed.path)
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                stripped_path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )

    def strip_processing_suffix_from_url(self, image_url: str) -> str:
        parsed = urlparse(image_url)
        stripped_path = self.strip_post_extension_transform_suffix(parsed.path)
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                stripped_path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )

    def remove_resize_query_params(self, image_url: str) -> str:
        parsed = urlparse(image_url)
        filtered_query = self.filter_resize_query(parsed.query)
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                filtered_query,
                parsed.fragment,
            )
        )
