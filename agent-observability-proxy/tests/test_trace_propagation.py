"""M3 tests: one trace ID across Agent A -> proxy -> Agent B -> proxy -> upstream."""
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

# urllib honors NO_PROXY and would bypass the loopback test proxy;
# drop it so the suite never depends on ambient proxy config (N7).
os.environ.pop("NO_PROXY", None); os.environ.pop("no_proxy", None)

import agent_b as agent_b_module
import proxy as proxy_module
import server as server_module


class M3TracePropagationTest(unittest.TestCase):
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
        cls.agent_b = agent_b_module.serve(
            "127.0.0.1", 0,
            proxy_url=f"http://127.0.0.1:{cls.proxy_port}",
            upstream_base=f"http://127.0.0.1:{cls.upstream_port}")
        cls.agent_b_port = cls.agent_b.server_address[1]
        threading.Thread(target=cls.agent_b.serve_forever, daemon=True).start()
        cls.opener = urllib.request.build_opener(urllib.request.ProxyHandler(
            {"http": f"http://127.0.0.1:{cls.proxy_port}"}))

    @classmethod
    def tearDownClass(cls):
        cls.agent_b.shutdown(); cls.proxy.shutdown(); cls.upstream.shutdown()
        cls.agent_b.server_close(); cls.proxy.server_close(); cls.upstream.server_close()
        cls.proxy.state.conn.close()
        cls.tmp.cleanup()

    def rows(self, trace_id=None):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        sql = "SELECT * FROM attempts ORDER BY id"
        out = conn.execute(sql).fetchall()
        conn.close()
        if trace_id is not None:
            out = [r for r in out if r["trace_id"] == trace_id]
        return out

    def call_agent_a(self, trace=None, data=None, headers=None):
        """Agent A: call Agent B through the proxy."""
        url = f"http://127.0.0.1:{self.agent_b_port}/task"
        req = urllib.request.Request(url, data=data,
                                     method="POST" if data else "GET")
        if trace:
            req.add_header("X-Trace-Id", trace)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        with self.opener.open(req, timeout=10) as resp:
            return resp.status, dict(resp.headers), json.loads(resp.read())

    def assert_two_legs(self, trace_id):
        legs = self.rows(trace_id)
        self.assertEqual(len(legs), 2, f"trace {trace_id}: {legs}")
        a_leg = [r for r in legs if r["endpoint"] == "/task"]
        b_leg = [r for r in legs if r["endpoint"] == "/echo"]
        self.assertEqual(len(a_leg), 1)
        self.assertEqual(len(b_leg), 1)
        self.assertIn(str(self.agent_b_port), a_leg[0]["dest_host"])
        self.assertIn(str(self.upstream_port), b_leg[0]["dest_host"])
        self.assertEqual(a_leg[0]["task_number"], b_leg[0]["task_number"])
        for row in legs:
            self.assertEqual(row["status"], "success")
            self.assertGreaterEqual(row["latency_seconds"], 0)
            self.assertGreater(row["bytes_out"], 0)
        return legs

    def test_explicit_trace_carried_across_both_legs_no_secrets(self):
        status, _, body = self.call_agent_a(
            trace="trace-m3-task-1",
            data=b"SECRET_PROMPT_BODY_12345",
            headers={"Authorization": "Bearer [REDACTED]"})
        self.assertEqual(status, 200)
        self.assertEqual(body["trace_id"], "trace-m3-task-1")
        self.assert_two_legs("trace-m3-task-1")
        dump = "\n".join(str(r) for r in self.rows())
        self.assertNotIn("SECRET_PROMPT_BODY_12345", dump)
        self.assertNotIn("SECRET_KEY_67890", dump)
        self.assertNotIn("Authorization", dump)

    def test_generated_trace_carried_on_second_leg(self):
        status, headers, body = self.call_agent_a()
        self.assertEqual(status, 200)
        generated = headers.get("X-Trace-Id")
        self.assertTrue(generated)
        self.assertEqual(body["trace_id"], generated)
        self.assert_two_legs(generated)

    def test_second_task_gets_different_trace(self):
        self.call_agent_a(trace="trace-m3-task-2")
        self.assert_two_legs("trace-m3-task-2")
        traces = {r["trace_id"] for r in self.rows()}
        self.assertIn("trace-m3-task-1", traces | {"trace-m3-task-1"})
        task2 = {r["trace_id"] for r in self.rows("trace-m3-task-2")}
        self.assertEqual(task2, {"trace-m3-task-2"})
        self.assertNotEqual("trace-m3-task-2", "trace-m3-task-1")


if __name__ == "__main__":
    unittest.main()
