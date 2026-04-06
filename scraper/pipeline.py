from scraper.adapters.registry import AdapterRegistry
from scraper.extractor import ImageExtractor
from scraper.original_resolver import OriginalImageResolver


class ScrapePipeline:
    def __init__(
        self,
        session,
        extractor_factory=ImageExtractor,
        browser_extractor_factory=None,
        resolver=None,
        adapter_registry=None,
        status_callback=None,
    ):
        self.session = session
        self.extractor_factory = extractor_factory
        self.browser_extractor_factory = browser_extractor_factory
        self.resolver = resolver or OriginalImageResolver()
        self.adapter_registry = adapter_registry or AdapterRegistry()
        self.status_callback = status_callback

    def emit_status(self, message: str):
        if self.status_callback:
            self.status_callback(message)

    def resolve(self, page_url: str, mode: str = "static", image_urls=None):
        return self.resolve_result(page_url, mode=mode, image_urls=image_urls).image_urls

    def resolve_result(self, page_url: str, mode: str = "static", image_urls=None):
        adapter = self.create_adapter(page_url)
        return adapter.extract(page_url, mode=mode, image_urls=image_urls)

    def create_adapter(self, page_url: str):
        return self.adapter_registry.create_adapter(
            page_url,
            session=self.session,
            extractor_factory=self.extractor_factory,
            browser_extractor_factory=self.browser_extractor_factory,
            resolver=self.resolver,
            status_callback=self.status_callback,
        )
