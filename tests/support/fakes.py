from scraper.models import ExtractionResult, ImageCandidate


class DummyCookie:
    def __init__(self, name, value, domain="example.com", path="/", secure=False):
        self.name = name
        self.value = value
        self.domain = domain
        self.path = path
        self.secure = secure


class DummyCookies:
    def __init__(self):
        self.items = []

    def set(self, name, value, domain=None, path="/", secure=False):
        self.items.append((name, value, domain, path, secure))

    def __iter__(self):
        return iter(
            DummyCookie(name, value, domain=domain, path=path, secure=secure)
            for name, value, domain, path, secure in self.items
        )


class DummySession:
    def __init__(self):
        self.cookies = DummyCookies()
        self.headers = {}


def make_candidate(url: str, source: str = "fake", is_primary: bool = False):
    return ImageCandidate(
        url=url,
        identity=url,
        source=source,
        is_primary=is_primary,
    )


def make_extraction_result(
    urls=None,
    primary_urls=None,
    source: str = "fake",
    used_browser: bool = False,
    metadata=None,
):
    return ExtractionResult(
        candidates=[make_candidate(url, source=source) for url in (urls or [])],
        primary_candidates=[
            make_candidate(url, source=source, is_primary=True)
            for url in (primary_urls or [])
        ],
        used_browser=used_browser,
        metadata=dict(metadata or {}),
    )


def make_static_extractor(urls):
    class ConfiguredStaticExtractor:
        def __init__(self, session):
            self.session = session
            self.requested_urls = []

        def extract_from_page(self, page_url: str):
            self.requested_urls.append(page_url)
            return list(urls)

    return ConfiguredStaticExtractor


def make_result_extractor(result):
    class ConfiguredResultExtractor:
        def __init__(self, session):
            self.session = session
            self.requested_urls = []

        def extract_result_from_page(self, page_url: str):
            self.requested_urls.append(page_url)
            return result

    return ConfiguredResultExtractor


class FakeBrowserExtractor:
    def __init__(self, urls=None, result=None, authenticated_session=None):
        self.urls = list(urls or [])
        self.result = result
        self.authenticated_session = authenticated_session or DummySession()
        self.primary_network_image_urls = list(
            (result.primary_image_urls if result else [])
        )
        self.opened = []
        self.closed = False
        self.requested_urls = []

    def open_page(self, page_url: str, headless: bool = False):
        self.opened.append((page_url, headless))

    def extract_result_from_current_page(self, page_url: str):
        self.requested_urls.append(page_url)
        if self.result is not None:
            return self.result
        return make_extraction_result(
            urls=self.urls,
            primary_urls=self.primary_network_image_urls,
            source="fake:browser",
            used_browser=True,
        )

    def extract_from_current_page(self, page_url: str):
        self.requested_urls.append(page_url)
        return list(self.urls)

    def build_authenticated_session(self):
        return self.authenticated_session

    def close(self):
        self.closed = True


class FakeAdapter:
    def __init__(self, result=None):
        self.calls = []
        self.next_result = result or make_extraction_result(
            urls=["https://cdn.example.com/a.jpg"],
            source="fake:adapter",
        )

    def extract(self, page_url: str, mode: str = "static", image_urls=None):
        self.calls.append((page_url, mode, image_urls))
        return self.next_result


class FakeRegistry:
    def __init__(self, adapter=None):
        self.adapter = adapter or FakeAdapter()
        self.calls = []

    def create_adapter(self, page_url: str, **adapter_kwargs):
        self.calls.append((page_url, adapter_kwargs))
        return self.adapter
