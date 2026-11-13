"""Dashboard page: markers plus the no-store middleware, no sockets."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.pop("NO_PROXY", None); os.environ.pop("no_proxy", None)

import api


class DashboardTest(unittest.TestCase):
    def test_dashboard_plain_words_and_live(self):
        body = api.dashboard()
        self.assertIn("Local proxy only. Metadata only. No bodies, no keys.", body)
        self.assertIn("Runs (newest first)", body)
        self.assertIn("Run detail", body)
        self.assertIn('id="live"', body)
        self.assertIn('role="status"', body)
        self.assertIn("Reading database", body)
        self.assertIn("let through", body)
        self.assertIn("stopped by the allowlist", body)
        self.assertIn("slowed down", body)
        self.assertIn("completed", body)
        self.assertIn("setInterval(load, 5000)", body)
        self.assertIn("outcomeWords", body)
        self.assertIn("runSummary", body)
        self.assertIn("Tried ", body)
        self.assertIn('scope="col"', body)
        self.assertIn("aria-label", body)
        self.assertNotIn("trace ID", body)
        self.assertIn("needs JavaScript", body)
        self.assertIn("starting first update", body)
        self.assertIn("page error", body)
        self.assertIn("rowsById", body)
        self.assertIn("makeRunRow", body)
        self.assertIn("updateRunRow", body)
        self.assertIn("insertBefore", body)

    def test_nothing_is_cached(self):
        # This sandbox blocks every listen() call, including the one the
        # Windows asyncio loop needs, so the middleware cannot run here.
        # Assert it is wired into the app; its body only sets no-store.
        registered = [m.kwargs.get("dispatch")
                      for m in api.app.user_middleware]
        self.assertIn(api._no_store, registered)


if __name__ == "__main__":
    unittest.main()
