"""
Shared audit engine: ONE Chrome for every audit, in every browser tab.

Before version 0.21 each audit (and each browser tab of the website)
opened its own Chrome with the same saved profile, and its own image
reader. Two tabs meant two Chromes fighting over one profile and two
image readers fighting over the processor, so both became very slow.

Now:
- One background thread owns the only Chrome. Every audit, from any
  tab, sends its products here. Products of different audits take
  turns, so two parents audited at the same time both move forward.
- Chrome only READS pages (read_product_page). The checks that do not
  need Chrome (downloads, design, image text, spelling, specification)
  run in a small background pool (analyse_product), while Chrome is
  already reading the next product. Upcoming products load in advance.
- Chrome stays open between audits (no start-up wait) and closes by
  itself after a few idle minutes. When another tool needs the saved
  profile (Verify Location, Variation Matrix), the engine closes Chrome
  between two products and lets it through.

The website calls run_batch_audit() (services/batch_audit_service.py),
which uses get_engine().submit(...) and waits for the results.
"""

import itertools
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from modules.amazon_session import AmazonBrowser, PROFILE_GATE, PREFETCH_AHEAD
from services.audit_service import read_product_page, analyse_product


# Chrome closes after this many idle seconds (it reopens when needed).
IDLE_CLOSE_SECONDS = 300

# Products analysed at the same time (downloads, design, image text...).
ANALYSIS_WORKERS = 2

STOP_STATUS = "LOCATION NOT VERIFIED"


class Batch:
    """One audit (a list of products) sent to the engine."""

    _ids = itertools.count(1)

    def __init__(self, items, audit_type, spec, check_design, check_text):
        self.id = next(self._ids)
        self.items = list(items)
        self.audit_type = audit_type
        self.spec = spec
        self.check_design = check_design
        self.check_text = check_text
        self.next_index = 0                      # next product for Chrome
        self.results = [None] * len(self.items)
        self.pages_read = 0
        self.finished = 0
        self.stopped = ""                        # reason, when stopped early
        self.cancelled = False
        self.started = time.perf_counter()
        self.ended = None
        self.done = threading.Event()
        self._lock = threading.Lock()

    # ----- used by the engine -----

    def has_pending(self):
        return not self.stopped and not self.cancelled and self.next_index < len(self.items)

    def _set(self, index, result):
        with self._lock:
            if self.results[index] is None:
                self.results[index] = result
                self.finished += 1
            if self.finished == len(self.items):
                self.ended = time.perf_counter()
                self.done.set()

    def stop(self, reason, status="FAILED"):
        """Every product not read yet gets a short 'not checked' result."""

        with self._lock:
            self.stopped = self.stopped or reason
            remaining = range(self.next_index, len(self.items))
            self.next_index = len(self.items)

        for index in remaining:
            item = self.items[index]
            row = failed_result(item, "Not checked. " + reason)
            row["overall_status"] = status
            self._set(index, row)

    # ----- used by the website -----

    def progress(self):
        """(pages read, products finished, total)."""
        return self.pages_read, self.finished, len(self.items)

    def wait(self, progress_callback=None, poll=0.3):
        """Block until every product is finished. Returns the results in order."""

        last = None

        while not self.done.wait(poll):
            state = self.progress()
            if progress_callback and state != last:
                last = state
                progress_callback(*state)

        if progress_callback:
            progress_callback(*self.progress())

        return list(self.results)

    def elapsed(self):
        return round((self.ended or time.perf_counter()) - self.started, 1)


def failed_result(item, message):
    """A result row for a product that could not be audited."""

    return {
        "product_url": item.get("url", ""),
        "overall_status": "FAILED",
        "errors": [message],
        "buy_box": {},
        "content": {},
        "spelling": {},
        "spec_check": {},
        "quality": [],
        "asin": item.get("asin", ""),
    }


class AuditEngine:

    def __init__(self):
        self._lock = threading.Condition()
        self._batches = []                       # active batches, in turn order
        self._turn = 0
        self._browser = None
        self._holding_profile = False
        self._last_work = time.monotonic()
        self._stopping = False
        self._pool = ThreadPoolExecutor(max_workers=ANALYSIS_WORKERS,
                                        thread_name_prefix="audit-analysis")
        self._thread = threading.Thread(target=self._run, name="audit-chrome", daemon=True)
        self._thread.start()

    # ---------- public ----------

    def submit(self, items, audit_type="Full Listing Audit", spec=None,
               check_design=False, check_text=False):
        """Queue an audit. Returns a Batch; call batch.wait() for the results."""

        batch = Batch(items, audit_type, spec, check_design, check_text)

        if not batch.items:
            batch.ended = time.perf_counter()
            batch.done.set()
            return batch

        with self._lock:
            self._batches.append(batch)
            self._lock.notify_all()

        return batch

    def shutdown(self):
        """Close Chrome and stop the engine (tests, app exit)."""

        with self._lock:
            self._stopping = True
            self._lock.notify_all()

        self._thread.join(timeout=30)
        self._pool.shutdown(wait=True)

    def cancel(self, batch):
        batch.cancelled = True
        batch.stop("Stopped by you.", "FAILED")

    def status(self):
        """Short text for the sidebar."""

        with self._lock:
            active = [b for b in self._batches if not b.done.is_set()]

        if not active:
            return "Idle" + (" (Chrome open)" if self._browser else "")

        left = sum(len(b.items) - b.finished for b in active)

        return f"{len(active)} audit(s) running, {left} product(s) left"

    # ---------- the Chrome thread ----------

    def _next_job(self):
        """Products of different audits take turns. Returns (batch, index) or None."""

        self._batches = [b for b in self._batches if b.has_pending() or not b.done.is_set()]

        ready = [b for b in self._batches if b.has_pending()]

        if not ready:
            return None

        batch = ready[self._turn % len(ready)]
        self._turn += 1

        index = batch.next_index
        batch.next_index += 1

        return batch, index

    def _upcoming(self, count):
        """The next product links in turn order (to load in advance)."""

        ready = [b for b in self._batches if b.has_pending()]

        urls = []
        positions = {b.id: b.next_index for b in ready}
        turn = self._turn

        while ready and len(urls) < count:
            batch = ready[turn % len(ready)]
            turn += 1
            index = positions[batch.id]
            if index < len(batch.items):
                urls.append(batch.items[index]["url"])
                positions[batch.id] = index + 1
            else:
                ready = [b for b in ready if positions[b.id] < len(b.items)]

        return urls

    def _open_browser(self):

        if self._browser is not None:
            return

        if not self._holding_profile:
            PROFILE_GATE.take()
            self._holding_profile = True

        browser = AmazonBrowser()
        browser.start()
        self._browser = browser

    def _close_browser(self):

        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._holding_profile:
            PROFILE_GATE.give()
            self._holding_profile = False

    def _run(self):

        while not self._stopping:

            # Someone else needs the saved profile: hand it over.
            if PROFILE_GATE.wanted() and self._holding_profile:
                self._close_browser()
                time.sleep(0.5)

            with self._lock:
                job = self._next_job()
                if job is None:
                    self._lock.wait(timeout=2)
                    idle = time.monotonic() - self._last_work > IDLE_CLOSE_SECONDS
                else:
                    upcoming = self._upcoming(PREFETCH_AHEAD)

            if job is None:
                if idle and self._browser is not None:
                    self._close_browser()
                continue

            batch, index = job
            item = batch.items[index]

            try:
                self._open_browser()
            except Exception as error:
                self._close_browser()
                batch._set(index, failed_result(item, "Browser could not start: " + str(error)))
                continue

            if batch.pages_read == 0:
                # A new audit may set the postcode again if Amazon lost it.
                self._browser.auto_set_tried = False
                self._browser.prompted = False

            self._browser.upcoming = upcoming
            self._browser.next_url = upcoming[0] if upcoming else None

            try:
                result = read_product_page(self._browser, item["url"], batch.audit_type,
                                           batch.check_design)
            except Exception as error:
                result = failed_result(item, "Unexpected error: " + str(error))
                self._close_browser()           # a clean Chrome for the next product

            result["asin"] = item.get("asin") or result.get("asin", "")
            batch.pages_read += 1
            self._last_work = time.monotonic()

            if result.get("overall_status") == STOP_STATUS:
                message = (result.get("errors") or ["Amazon is not using your saved postcode."])[0]
                batch._set(index, analyse_product(result))
                # Every other product would fail the same way.
                batch.stop(message, STOP_STATUS)
                continue

            self._pool.submit(self._analyse, batch, index, item, result)

        self._close_browser()

    def _analyse(self, batch, index, item, result):

        try:
            result = analyse_product(result, batch.spec, batch.check_design, batch.check_text)
        except Exception as error:
            result.setdefault("errors", []).append("Analysis failed: " + str(error))
            result.pop("_done", None)

        result["asin"] = item.get("asin") or result.get("asin", "")
        batch._set(index, result)


_ENGINE = None
_ENGINE_LOCK = threading.Lock()


def get_engine():
    """The one engine of this bot (created on first use)."""

    global _ENGINE

    with _ENGINE_LOCK:
        if _ENGINE is None:
            _ENGINE = AuditEngine()
        return _ENGINE


def reset_engine():
    """Stop the engine (it is created again on next use). Used by tests."""

    global _ENGINE

    with _ENGINE_LOCK:
        engine, _ENGINE = _ENGINE, None

    if engine is not None:
        engine.shutdown()
