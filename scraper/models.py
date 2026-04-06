from dataclasses import dataclass, field


@dataclass
class ImageCandidate:
    url: str
    identity: str
    score: int = 0
    source: str = "unknown"
    context: str = ""
    is_primary: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass
class ExtractionResult:
    candidates: list[ImageCandidate] = field(default_factory=list)
    primary_candidates: list[ImageCandidate] = field(default_factory=list)
    used_browser: bool = False
    metadata: dict = field(default_factory=dict)

    @property
    def image_urls(self) -> list[str]:
        return [candidate.url for candidate in self.candidates]

    @property
    def primary_image_urls(self) -> list[str]:
        return [candidate.url for candidate in self.primary_candidates]


@dataclass
class DownloadSummary:
    success_count: int
    converted_count: int = 0
