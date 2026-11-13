"""Cost calculation: priced, recorded, and unknown destinations."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.pop("NO_PROXY", None); os.environ.pop("no_proxy", None)

import db
import api


def _row(dest="127.0.0.1", outcome="allowed", status="success", cost=0.0):
    return {"dest_host": dest, "outcome": outcome, "status": status,
            "cost_dollars": cost}


class AttemptCostTest(unittest.TestCase):
    def test_blocked_is_free_even_without_a_price(self):
        self.assertEqual(api.attempt_cost(_row("pay.example.com", "blocked", "blocked")), 0.0)

    def test_rate_limited_is_free(self):
        self.assertEqual(api.attempt_cost(_row("pay.example.com", "rate_limited", "error")), 0.0)

    def test_loopback_is_free_with_or_without_port(self):
        for dest in ("127.0.0.1", "127.0.0.1:18080", "localhost", "localhost:8888", "::1"):
            self.assertEqual(api.attempt_cost(_row(dest)), 0.0, dest)

    def test_recorded_real_cost_wins_over_the_table(self):
        self.assertEqual(api.attempt_cost(_row("127.0.0.1", "allowed", "success", 0.002)), 0.002)

    def test_unknown_destination_is_none(self):
        self.assertIsNone(api.attempt_cost(_row("pay.example.com")))

    def test_failed_priced_attempt_keeps_its_price(self):
        self.assertEqual(api.attempt_cost(_row("127.0.0.1", "allowed", "error")), 0.0)


class CostLineTest(unittest.TestCase):
    def test_free_run_sentence(self):
        rows = [_row("127.0.0.1"), _row("example.com", "blocked", "blocked")]
        summary = api.summarize_costs(rows)
        self.assertEqual((summary["cost"], summary["wasted"]), (0.0, 0.0))
        self.assertEqual(api.run_cost_line(summary),
                         "this run cost $0.00, $0.00 of it was wasted on failed or blocked runs.")

    def test_unknown_sentence_names_the_destination(self):
        rows = [_row("pay.example.com"), _row("pay.example.com", "allowed", "error")]
        summary = api.summarize_costs(rows)
        self.assertIsNone(summary["cost"])
        self.assertIsNone(summary["wasted"])
        self.assertEqual(api.run_cost_line(summary),
                         "this run cost unknown (no price for pay.example.com), "
                         "and an unknown amount of it was wasted on failed or blocked runs.")

    def test_known_waste_beside_unknown_price(self):
        rows = [_row("pay.example.com"), _row("127.0.0.1", "allowed", "error")]
        summary = api.summarize_costs(rows)
        self.assertIsNone(summary["cost"])
        self.assertEqual(summary["wasted"], 0.0)


class CostEndpointsTest(unittest.TestCase):
    def test_endpoints_report_costs(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self.addCleanup(os.unlink, tmp.name)
        conn = db.init_db(tmp.name)
        db.log_attempt(conn, trace_id="t-paid", task_number=1, attempt=1,
                       status="success", dest_host="pay.example.com",
                       endpoint="/v1/x", method="POST", outcome="allowed")
        db.log_attempt(conn, trace_id="t-free", task_number=1, attempt=1,
                       status="blocked", dest_host="example.com",
                       endpoint="/", method="GET", outcome="blocked",
                       reason="not_allowlisted")
        conn.close()
        old, api.DB_PATH = api.DB_PATH, tmp.name
        self.addCleanup(setattr, api, "DB_PATH", old)
        paid = api.get_trace("t-paid")
        self.assertIsNone(paid["cost"])
        self.assertIn("no price for pay.example.com", paid["cost_line"])
        free = api.get_trace("t-free")
        self.assertEqual(free["cost"], 0.0)
        stats = api.stats()
        self.assertEqual(stats["unknown_runs"], 1)
        self.assertIsNone(stats["total_cost"])
        self.assertIn("no price for pay.example.com", stats["cost_line"])


if __name__ == "__main__":
    unittest.main()
