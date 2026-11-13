"""API endpoint shapes against a seeded throwaway database.

Calls the endpoint functions directly: the sandbox blocks even
loopback listen(), so no test here may open a socket.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.pop("NO_PROXY", None); os.environ.pop("no_proxy", None)

from fastapi import HTTPException

import db
import api

ALLOWED_KEYS = {
    "id", "trace_id", "attempt", "status", "latency_seconds",
    "created_at", "dest_host", "endpoint", "method", "bytes_in",
    "bytes_out", "http_status", "outcome", "reason", "attempt_count",
}


def _seed(path):
    conn = db.init_db(path)
    db.log_attempt(conn, trace_id="t-old", task_number=1, attempt=1,
                   status="blocked", latency_seconds=2.0,
                   dest_host="example.com", endpoint="/x", method="GET",
                   outcome="blocked", reason="not_allowlisted")
    for i in (1, 2):
        db.log_attempt(conn, trace_id="t-new", task_number=1,
                       attempt=i, status="success",
                       latency_seconds=0.5,
                       dest_host="127.0.0.1", endpoint="/ok",
                       method="GET", bytes_in=10, bytes_out=20,
                       http_status=200, outcome="allowed")
    conn.close()


class ApiShapeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        cls.db_path = tmp.name
        _seed(cls.db_path)
        cls._old_db_path = api.DB_PATH
        api.DB_PATH = cls.db_path

    @classmethod
    def tearDownClass(cls):
        api.DB_PATH = cls._old_db_path
        os.unlink(cls.db_path)

    def test_health(self):
        body = api.health()
        self.assertTrue(body["ok"])
        self.assertEqual(body["db"], self.db_path)

    def test_traces_newest_first(self):
        traces = api.list_traces()["traces"]
        self.assertEqual([t["trace_id"] for t in traces], ["t-new", "t-old"])
        self.assertEqual(traces[0]["attempt_count"], 2)
        for trace in traces:
            self.assertTrue(set(trace) <= ALLOWED_KEYS, set(trace) - ALLOWED_KEYS)

    def test_traces_limit(self):
        self.assertEqual(len(api.list_traces(limit=1)["traces"]), 1)
        with self.assertRaises(HTTPException) as ctx:
            api.list_traces(limit=200)
        self.assertEqual(ctx.exception.status_code, 422)

    def test_trace_detail_and_404(self):
        body = api.get_trace("t-new")
        self.assertEqual(len(body["attempts"]), 2)
        with self.assertRaises(HTTPException) as ctx:
            api.get_trace("nope")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_stats(self):
        self.assertEqual(api.stats(), {
            "total_attempts": 3,
            "allowed": 2,
            "blocked": 1,
            "rate_limited": 0,
            "successes": 2,
            "avg_latency_seconds": 1.0,
        })


class ApiRefreshTest(unittest.TestCase):
    """Rows the proxy writes after the first read must show up on refresh."""

    def test_new_rows_appear_on_next_read(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self.addCleanup(os.unlink, tmp.name)
        conn = db.init_db(tmp.name)
        db.log_attempt(conn, trace_id="t-first", task_number=1, attempt=1,
                       status="success", dest_host="127.0.0.1",
                       endpoint="/old", method="GET", outcome="allowed")
        old_db_path, api.DB_PATH = api.DB_PATH, tmp.name
        self.addCleanup(setattr, api, "DB_PATH", old_db_path)
        first = [t["trace_id"] for t in api.list_traces()["traces"]]
        self.assertEqual(first, ["t-first"])
        # proxy logs a later run; the next refresh must show it on top
        db.log_attempt(conn, trace_id="t-second", task_number=1, attempt=1,
                       status="success", dest_host="127.0.0.1",
                       endpoint="/new", method="GET", outcome="allowed")
        conn.close()
        second = [t["trace_id"] for t in api.list_traces()["traces"]]
        self.assertEqual(second, ["t-second", "t-first"])
        self.assertEqual(api.stats()["total_attempts"], 2)


if __name__ == "__main__":
    unittest.main()
