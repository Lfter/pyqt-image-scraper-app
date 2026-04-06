from scraper.adapters.generic import GenericSiteAdapter
from scraper.adapters.weibo import WeiboSiteAdapter


class AdapterRegistry:
    BUILTIN_ADAPTER_CLASSES = (WeiboSiteAdapter,)

    def __init__(self, adapter_classes=None, default_adapter_cls=GenericSiteAdapter):
        self.adapter_classes = list(adapter_classes or [])
        self.default_adapter_cls = default_adapter_cls

    def register(self, adapter_cls):
        self.adapter_classes.append(adapter_cls)

    def create_adapter(self, page_url: str, **adapter_kwargs):
        for adapter_cls in self.get_active_adapter_classes():
            if adapter_cls.matches(page_url):
                return adapter_cls(**adapter_kwargs)

        return self.default_adapter_cls(**adapter_kwargs)

    def get_registered_adapter_classes(self):
        return sorted(
            self.adapter_classes,
            key=lambda adapter_cls: getattr(adapter_cls, "priority", 0),
            reverse=True,
        )

    def get_active_adapter_classes(self):
        registered = self.get_registered_adapter_classes()
        active = list(registered)

        for adapter_cls in self.BUILTIN_ADAPTER_CLASSES:
            if adapter_cls not in active and adapter_cls is not self.default_adapter_cls:
                active.append(adapter_cls)

        return sorted(
            active,
            key=lambda adapter_cls: getattr(adapter_cls, "priority", 0),
            reverse=True,
        )
