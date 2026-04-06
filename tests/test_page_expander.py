import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.browser.expander import PageExpander


class FakePage:
    def __init__(self):
        self.timeouts = []

    def wait_for_timeout(self, milliseconds):
        self.timeouts.append(milliseconds)


class PageExpanderTests(unittest.TestCase):
    def test_expand_keeps_advancing_until_page_stabilizes(self):
        expander = PageExpander()
        page = FakePage()
        states = [
            {"moved": True, "clicked": False, "counts": (100, 101)},
            {"moved": True, "clicked": False, "counts": (100, 101)},
            {"moved": True, "clicked": False, "counts": (200, 201)},
            {"moved": False, "clicked": False, "counts": (200, 201)},
            {"moved": False, "clicked": False, "counts": (200, 201)},
            {"moved": False, "clicked": False, "counts": (200, 201)},
        ]
        round_index = {"value": 0}
        wait_calls = []
        current_counts = {"value": states[0]["counts"]}

        def scroll_action():
            state = states[round_index["value"]]
            current_counts["value"] = state["counts"]
            round_index["value"] += 1
            return state["moved"]

        def click_action():
            return states[round_index["value"] - 1]["clicked"]

        expander.expand(
            page=page,
            get_loaded_counts=lambda: current_counts["value"],
            wait_for_network=lambda: wait_calls.append(round_index["value"]),
            scroll_action=scroll_action,
            click_action=click_action,
        )

        self.assertEqual(round_index["value"], len(states))
        self.assertGreaterEqual(len(wait_calls), 3)
        self.assertEqual(page.timeouts.count(expander.POST_ACTION_SETTLE_MS), 5)

    def test_expand_returns_immediately_without_page(self):
        expander = PageExpander()

        expander.expand(
            page=None,
            get_loaded_counts=lambda: (0, 0),
            wait_for_network=lambda: None,
        )


if __name__ == "__main__":
    unittest.main()
