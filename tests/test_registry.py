import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.adapters.base import BaseSiteAdapter
from scraper.adapters.registry import AdapterRegistry
from scraper.adapters.weibo import WeiboSiteAdapter
from tests.contracts.registry_contract import RegistryContractMixin


class AdapterRegistryContractTests(RegistryContractMixin, unittest.TestCase):
    registry_cls = AdapterRegistry


class RegisteredAdapter(BaseSiteAdapter):
    name = "registered"
    priority = 10

    @classmethod
    def matches(cls, page_url: str) -> bool:
        return "registered.test" in page_url


class CustomFallbackAdapter(BaseSiteAdapter):
    name = "custom-fallback"
    priority = -1

    @classmethod
    def matches(cls, page_url: str) -> bool:
        del page_url
        return False


class AdapterRegistryTests(unittest.TestCase):
    def test_register_adds_adapter_class_to_registry(self):
        registry = AdapterRegistry()
        registry.register(RegisteredAdapter)

        self.assertEqual(registry.get_registered_adapter_classes(), [RegisteredAdapter])

    def test_create_adapter_uses_custom_default_adapter_when_provided(self):
        registry = AdapterRegistry(default_adapter_cls=CustomFallbackAdapter)

        adapter = registry.create_adapter("https://unknown.test/gallery", session=None)

        self.assertIsInstance(adapter, CustomFallbackAdapter)

    def test_create_adapter_selects_builtin_weibo_adapter(self):
        registry = AdapterRegistry()

        adapter = registry.create_adapter("https://m.weibo.cn/status/1234567890", session=None)

        self.assertIsInstance(adapter, WeiboSiteAdapter)


if __name__ == "__main__":
    unittest.main()
