"""Visualizer tests: headline math, A/B/C verdicts, demo-only, no secrets (v1), plus ordering, POST, collapsing (v2)."""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import db as db_module  # noqa: E402
import visualizer  # noqa: E402


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
            strategy="Bearer [REDACTED]",
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


class VisualizerV2Test(unittest.TestCase):
    """v2: A-first ordering, POST metadata-only, long-trace collapsing."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "attempts.db")
        self.conn = db_module.init_db(self.db_path)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_traces_sorted_a_first_despite_reverse_insertion(self):
        for tid, task in (("demo-trace-c", 3), ("demo-trace-b", 2), ("demo-trace-a", 1)):
            db_module.log_attempt(
                self.conn, trace_id=tid, task_number=task, attempt=1,
                status="success", latency_seconds=0.1, cost_dollars=0.001,
                dest_host="127.0.0.1:18080", endpoint="/echo",
                method="GET", http_status=200)
        rows = visualizer.fetch_demo_attempts(self.conn)
        traces = visualizer.group_traces(rows)
        self.assertEqual([t["trace_id"] for t in traces],
                         ["demo-trace-a", "demo-trace-b", "demo-trace-c"])
        self.assertEqual([t["label"] for t in traces], ["A", "B", "C"])
        md = visualizer.render_markdown(rows, traces)
        self.assertLess(md.index("Trace A"), md.index("Trace B"))
        self.assertLess(md.index("Trace B"), md.index("Trace C"))
        mermaid = visualizer.build_mermaid(traces)
        self.assertLess(mermaid.index("subgraph TA"), mermaid.index("subgraph TB"))
        self.assertLess(mermaid.index("subgraph TB"), mermaid.index("subgraph TC"))

    def test_post_shows_metadata_only_never_values_or_bodies(self):
        db_module.log_attempt(
            self.conn, trace_id="demo-trace-post", task_number=1, attempt=1,
            status="success", latency_seconds=0.25, cost_dollars=0.002,
            dest_host="127.0.0.1:18080",
            endpoint="/submit?token=SECRET123&user=bob",
            method="POST", bytes_in=100, bytes_out=200, http_status=200)
        rows = visualizer.fetch_demo_attempts(self.conn)
        traces = visualizer.group_traces(rows)
        md = visualizer.render_markdown(rows, traces)
        mermaid = visualizer.build_mermaid(traces)
        for text in (md, mermaid):
            self.assertIn("POST", text)
            self.assertIn("/submit", text)
            self.assertIn("2 args", text)
            self.assertIn("100B in / 200B out", text)
            for banned in ("SECRET123", "token=", "user=", "bob"):
                self.assertNotIn(banned, text)

    def test_long_trace_collapses_middle_retries_but_counts_stay_true(self):
        for attempt in range(1, 11):
            db_module.log_attempt(
                self.conn, trace_id="demo-trace-long", task_number=1,
                attempt=attempt, status="failure", latency_seconds=0.1,
                cost_dollars=0.001, retry_reason="retry" if attempt > 1 else "",
                dest_host="127.0.0.1:18080", endpoint="/fail",
                method="GET", http_status=500)
        rows = visualizer.fetch_demo_attempts(self.conn)
        traces = visualizer.group_traces(rows)
        self.assertEqual(len(traces[0]["steps"]), 10)
        mermaid = visualizer.build_mermaid(traces)
        self.assertIn("collapsed", mermaid)
        self.assertEqual(mermaid.count("Attempt"), 3)
        md = visualizer.render_markdown(rows, traces)
        self.assertIn("| Trace A | 10 | 9 |", md)
        h = visualizer.headline(rows, traces)
        self.assertEqual(h["total_attempts"], 10)
        self.assertEqual(h["total_retries"], 9)


if __name__ == "__main__":
    unittest.main()
