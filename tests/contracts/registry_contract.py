import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.adapters.base import BaseSiteAdapter
from scraper.adapters.generic import GenericSiteAdapter


class RegistryContractMixin:
    registry_cls = None

    def create_registry(self, *args, **kwargs):
        if self.registry_cls is None:
            raise AssertionError("registry_cls must be set on the contract test case")
        return self.registry_cls(*args, **kwargs)

    def test_contract_returns_generic_fallback_when_no_custom_adapter_matches(self):
        registry = self.create_registry()

        adapter = registry.create_adapter("https://unknown.test/gallery", session=None)

        self.assertIsInstance(adapter, GenericSiteAdapter)

    def test_contract_prefers_highest_priority_match(self):
        class ExampleAdapter(BaseSiteAdapter):
            name = "example"
            priority = 20

            @classmethod
            def matches(cls, page_url: str) -> bool:
                return "example.com" in page_url

        class LowPriorityAdapter(BaseSiteAdapter):
            name = "low-priority"
            priority = 5

            @classmethod
            def matches(cls, page_url: str) -> bool:
                return "example.com" in page_url

        registry = self.create_registry([LowPriorityAdapter, ExampleAdapter])

        adapter = registry.create_adapter("https://example.com/gallery", session=None)

        self.assertIsInstance(adapter, ExampleAdapter)
