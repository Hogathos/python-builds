"""Visualizer v1 tests: headline math, A/B/C verdicts, demo-only, no secrets."""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import db as db_module
import visualizer


class VisualizerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "attempts.db")
        self.conn = db_module.init_db(self.db_path)
        visualizer.seed_demo(self.conn)
        # Real-traffic row that must be excluded, plus secret-shaped values
        # in fields the visualizer must never read out.
        db_module.log_attempt(
            self.conn, trace_id="real-trace-x", task_number=99, attempt=1,
            status="success", latency_seconds=9.9, cost_dollars=99.0,
            strategy="Bearer SECRET_KEY_SHOULD_NOT_APPEAR",
            dest_host="api.example-real.com", endpoint="/v1/chat",
            method="POST", http_status=200)
        self.rows = visualizer.fetch_demo_attempts(self.conn)
        self.traces = visualizer.group_traces(self.rows)
        self.md = visualizer.render_markdown(self.rows, self.traces)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_headline_numbers(self):
        h = visualizer.headline(self.rows, self.traces)
        self.assertEqual(h["total_attempts"], 6)
        self.assertEqual(h["total_tasks"], 3)
        self.assertEqual(h["successful_tasks"], 2)
        self.assertAlmostEqual(h["success_rate"], 200.0 / 3.0)
        self.assertEqual(h["total_retries"], 3)
        self.assertAlmostEqual(h["total_cost"], 0.012)
        self.assertAlmostEqual(h["cost_per_success"], 0.006)

    def test_verdicts_are_a_retried_b_clean_c_wasted(self):
        verdicts = {t["label"]: visualizer.trace_verdict(t) for t in self.traces}
        self.assertEqual(verdicts["A"], "RETRIED THEN SUCCEEDED")
        self.assertEqual(verdicts["B"], "CLEAN SUCCESS")
        self.assertEqual(verdicts["C"], "WASTED - NEVER SUCCEEDED")
        self.assertIn("Trace A", self.md)
        self.assertIn("Trace C - WASTED - NEVER SUCCEEDED", self.md)

    def test_demo_only_real_traffic_excluded(self):
        self.assertNotIn("real-trace-x", self.md)
        self.assertNotIn("api.example-real.com", self.md)
        self.assertNotIn("99", visualizer.build_mermaid(self.traces))

    def test_no_secrets_headers_or_bodies_in_output(self):
        for banned in ("Authorization", "Bearer", "SECRET_KEY", "prompt"):
            self.assertNotIn(banned, self.md)

    def test_mermaid_shape_retries_cost_latency(self):
        mermaid = visualizer.build_mermaid(self.traces)
        self.assertTrue(mermaid.startswith("flowchart TD"))
        self.assertIn("classDef success", mermaid)
        self.assertIn("classDef failure", mermaid)
        self.assertEqual(mermaid.count("-->|retry|"), 3)
        self.assertIn("cost $0.0020 - latency 0.42s", mermaid)
        self.assertIn("HTTP 500", mermaid)


if __name__ == "__main__":
    unittest.main()
