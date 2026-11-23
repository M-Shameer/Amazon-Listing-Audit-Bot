"""Shared audit engine: one Chrome for several audits at once (no real browser)."""

import threading
import time
import unittest
from unittest import mock

from services import audit_engine
from modules.amazon_session import PROFILE_GATE


class FakeBrowser:
    starts = 0
    order = []

    def __init__(self):
        self.upcoming = []
        self.next_url = None
        self.auto_set_tried = False
        self.prompted = False

    def start(self):
        FakeBrowser.starts += 1

    def close(self):
        pass


def fake_read(browser, url, *args, **kwargs):
    FakeBrowser.order.append(url)
    time.sleep(0.01)
    return {"product_url": url, "overall_status": "NO RULE-BASED ISSUES FOUND", "errors": [],
            "_done": False, "content": {}, "content_display": {}, "design_check": {},
            "timings": {}, "buy_box": {}}


def fake_analyse(result, *args, **kwargs):
    result.pop("_done", None)
    time.sleep(0.02)
    result["analysed"] = True
    return result


def items(prefix, count):
    return [{"url": f"https://www.amazon.co.uk/dp/{prefix}{n:08d}", "asin": f"{prefix}{n:08d}"}
            for n in range(count)]


class EngineTests(unittest.TestCase):

    def setUp(self):
        audit_engine.reset_engine()
        FakeBrowser.starts = 0
        FakeBrowser.order = []
        self.patches = [
            mock.patch.object(audit_engine, "AmazonBrowser", FakeBrowser),
            mock.patch.object(audit_engine, "read_product_page", fake_read),
            mock.patch.object(audit_engine, "analyse_product", fake_analyse),
        ]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        audit_engine.reset_engine()
        for patch in self.patches:
            patch.stop()

    def test_two_audits_share_one_chrome_and_take_turns(self):
        engine = audit_engine.get_engine()
        first = engine.submit(items("A1", 4))
        second = engine.submit(items("B1", 4))

        results_a = first.wait()
        results_b = second.wait()

        self.assertEqual(FakeBrowser.starts, 1)
        self.assertTrue(all(r["analysed"] for r in results_a + results_b))
        # Results come back in the order the products were given.
        self.assertEqual([r["asin"] for r in results_a], [i["asin"] for i in items("A1", 4)])
        # Turns alternate: B's first product is read before A's last.
        self.assertLess(FakeBrowser.order.index(items("B1", 4)[0]["url"]),
                        FakeBrowser.order.index(items("A1", 4)[3]["url"]))

    def test_other_tool_gets_the_profile(self):
        engine = audit_engine.get_engine()
        engine.submit(items("C1", 2)).wait()      # Chrome is now open and holds the profile

        got = []

        def other_tool():
            with PROFILE_GATE.exclusive(timeout=10):
                got.append(True)

        thread = threading.Thread(target=other_tool)
        thread.start()
        thread.join(timeout=10)

        self.assertEqual(got, [True])

        # The engine opens Chrome again for the next audit.
        engine.submit(items("D1", 1)).wait()
        self.assertEqual(FakeBrowser.starts, 2)

    def test_upcoming_products_are_loaded_ahead(self):
        engine = audit_engine.get_engine()
        with engine._lock:
            engine._batches.append(audit_engine.Batch(items("E1", 5), "x", None, False, False))
            self.assertEqual(len(engine._upcoming(3)), 3)


if __name__ == "__main__":
    unittest.main()
