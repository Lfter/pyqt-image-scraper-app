import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.adapters.generic import GenericSiteAdapter
from tests.contracts.adapter_contract import AdapterContractMixin


class GenericSiteAdapterContractTests(AdapterContractMixin, unittest.TestCase):
    adapter_cls = GenericSiteAdapter
