from scraper.adapters.base import BaseSiteAdapter
from scraper.adapters.generic import GenericSiteAdapter
from scraper.adapters.registry import AdapterRegistry
from scraper.adapters.weibo import WeiboSiteAdapter

__all__ = [
    "AdapterRegistry",
    "BaseSiteAdapter",
    "GenericSiteAdapter",
    "WeiboSiteAdapter",
]
