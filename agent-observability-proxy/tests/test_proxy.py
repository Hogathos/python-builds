"""M1 tests: run with `python -m pytest tests/` or `python -m unittest`."""
import http.client
import json
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import proxy as proxy_module
import server as server_module


class M1ProxyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.tmp.name, "attempts.db")
        cls.upstream = ThreadingHTTPServer(("127.0.0.1", 0), server_module.Handler)
        cls.upstream_port = cls.upstream.server_address[1]
        threading.Thread(target=cls.upstream.serve_forever, daemon=True).start()
        cls.proxy = proxy_module.serve("127.0.0.1", 0, cls.db_path)
        cls.proxy_port = cls.proxy.server_address[1]
        threading.Thread(target=cls.proxy.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.upstream_port}"
        cls.opener = urllib.request.build_opener(urllib.request.ProxyHandler(
            {"http": f"http://127.0.0.1:{cls.proxy_port}"}))

    @classmethod
    def tearDownClass(cls):
        cls.proxy.shutdown(); cls.upstream.shutdown()
        cls.proxy.server_close(); cls.upstream.server_close()
        cls.proxy.state.conn.close()
        cls.tmp.cleanup()

    def rows(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        out = conn.execute("SELECT * FROM attempts ORDER BY id").fetchall()
        conn.close()
        return out

    def get(self, path, trace=None, data=None, headers=None):
        req = urllib.request.Request(self.base + path, data=data,
                                     method="POST" if data else "GET")
        if trace:
            req.add_header("X-Trace-Id", trace)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with self.opener.open(req, timeout=10) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_generated_trace_is_forwarded_and_logged(self):
        before = len(self.rows())
        status, headers, body = self.get("/echo")
        self.assertEqual(status, 200)
        generated = headers.get("X-Trace-Id")
        self.assertTrue(generated)
        self.assertEqual(json.loads(body)["trace_id"], generated)
        row = self.rows()[before]
        self.assertEqual(row["trace_id"], generated)
        self.assertEqual(row["method"], "GET")
        self.assertEqual(row["endpoint"], "/echo")
        self.assertIn("127.0.0.1", row["dest_host"])
        self.assertEqual(row["status"], "success")
        self.assertEqual(row["http_status"], 200)
        self.assertGreaterEqual(row["bytes_out"], len(body) - 5)
        self.assertGreaterEqual(row["latency_seconds"], 0)

    def test_existing_trace_kept_unchanged_and_retry_grouping(self):
        status, _, body = self.get("/echo", trace="trace-keep-1")
        self.assertEqual(json.loads(body)["trace_id"], "trace-keep-1")
        self.get("/echo", trace="trace-keep-1")
        mine = [r for r in self.rows() if r["trace_id"] == "trace-keep-1"]
        self.assertEqual([r["attempt"] for r in mine], [1, 2])
        self.assertEqual(mine[1]["retry_reason"], "retry")
        self.assertEqual(mine[0]["task_number"], mine[1]["task_number"])

    def test_secrets_and_bodies_never_logged(self):
        secret_body = b"SECRET_PROMPT_BODY_12345"
        self.get("/echo", trace="trace-secret",
                 data=secret_body,
                 headers={"Authorization": "Bearer SECRET_KEY_67890"})
        conn = sqlite3.connect(self.db_path)
        dump = "\n".join(str(r) for r in conn.execute("SELECT * FROM attempts"))
        conn.close()
        self.assertNotIn("SECRET_PROMPT_BODY_12345", dump)
        self.assertNotIn("SECRET_KEY_67890", dump)
        row = [r for r in self.rows() if r["trace_id"] == "trace-secret"][0]
        self.assertEqual(row["bytes_in"], len(secret_body))

    def test_failure_status_and_usage_tokens(self):
        status, _, _ = self.get("/fail", trace="trace-fail")
        self.assertEqual(status, 500)
        row = [r for r in self.rows() if r["trace_id"] == "trace-fail"][0]
        self.assertEqual((row["status"], row["http_status"]), ("failure", 500))
        self.assertEqual(row["input_tokens"], 0)

        self.get("/usage", trace="trace-usage")
        row = [r for r in self.rows() if r["trace_id"] == "trace-usage"][0]
        self.assertEqual(row["input_tokens"], 42)  # only because upstream reported it
        self.assertEqual(row["cost_dollars"], 0.0)

    def test_malformed_content_length_gets_400_and_log_row(self):
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.proxy_port, timeout=10)
        conn.request("GET", f"{self.base}/echo",
                     headers={"Content-Length": "abc",
                              "X-Trace-Id": "trace-malformed-cl"})
        resp = conn.getresponse()
        resp.read()
        self.assertEqual(resp.status, 400)
        self.assertEqual(resp.getheader("X-Trace-Id"), "trace-malformed-cl")
        conn.close()
        rows = [r for r in self.rows()
                if r["trace_id"] == "trace-malformed-cl"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["http_status"], 400)
        self.assertEqual(rows[0]["reason"], "malformed_header")
        self.assertEqual((rows[0]["bytes_in"], rows[0]["bytes_out"]), (0, 0))

    def test_malformed_host_port_gets_400_and_log_row(self):
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.proxy_port, timeout=10)
        conn.putrequest("GET", "/echo", skip_host=1)
        conn.putheader("Host", "127.0.0.1:abc")
        conn.putheader("X-Trace-Id", "trace-malformed-host")
        conn.endheaders()
        resp = conn.getresponse()
        resp.read()
        self.assertEqual(resp.status, 400)
        conn.close()
        rows = [r for r in self.rows()
                if r["trace_id"] == "trace-malformed-host"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["http_status"], 400)
        self.assertEqual(rows[0]["reason"], "malformed_header")
        self.assertEqual((rows[0]["bytes_in"], rows[0]["bytes_out"]), (0, 0))

        conn2 = http.client.HTTPConnection(
            "127.0.0.1", self.proxy_port, timeout=10)
        conn2.request("GET", "http://127.0.0.1:abc/echo",
                      headers={"X-Trace-Id": "trace-malformed-urlport"})
        resp2 = conn2.getresponse()
        resp2.read()
        self.assertEqual(resp2.status, 400)
        conn2.close()
        rows2 = [r for r in self.rows()
                 if r["trace_id"] == "trace-malformed-urlport"]
        self.assertEqual(len(rows2), 1)
        self.assertEqual(rows2[0]["reason"], "malformed_header")

    # CONNECT tunnelling (M2) is covered in tests/test_connect.py.


if __name__ == "__main__":
    unittest.main()
