from scraper.adapters.base import BaseSiteAdapter


class GenericSiteAdapter(BaseSiteAdapter):
    name = "generic"
    priority = -1000

    @classmethod
    def matches(cls, page_url: str) -> bool:
        del page_url
        return True
