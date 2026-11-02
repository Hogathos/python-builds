"""M3 demo: Agent A -> proxy -> Agent B -> proxy -> upstream, one trace.

Runs the whole local chain in-process (test server, proxy, Agent B on
ephemeral loopback ports, temp SQLite file), makes two separate tasks,
and prints the metadata rows so the shared trace ID can be checked.

Run:  python demo_two_agents.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import threading
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import agent_b as agent_b_module
import proxy as proxy_module
import server as server_module


def main():
    tmp = tempfile.TemporaryDirectory()
    db_path = os.path.join(tmp.name, "attempts.db")
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), server_module.Handler)
    upstream_port = upstream.server_address[1]
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    proxy = proxy_module.serve("127.0.0.1", 0, db_path)
    proxy_port = proxy.server_address[1]
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    agent_b = agent_b_module.serve(
        "127.0.0.1", 0, proxy_url=f"http://127.0.0.1:{proxy_port}",
        upstream_base=f"http://127.0.0.1:{upstream_port}")
    agent_b_port = agent_b.server_address[1]
    threading.Thread(target=agent_b.serve_forever, daemon=True).start()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(
        {"http": f"http://127.0.0.1:{proxy_port}"}))

    def agent_a(trace=None):
        req = urllib.request.Request(
            f"http://127.0.0.1:{agent_b_port}/task", method="GET")
        if trace:
            req.add_header("X-Trace-Id", trace)
        with opener.open(req, timeout=10) as resp:
            return resp.headers.get("X-Trace-Id"), json.loads(resp.read())

    try:
        returned1, body1 = agent_a()  # no trace sent: proxy generates one
        returned2, _ = agent_a(trace="demo-m3-task-2")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM attempts ORDER BY id").fetchall()
        conn.close()
        print(f"task 1 trace (generated): {returned1}  agent B saw: {body1['trace_id']}")
        print(f"task 2 trace (explicit):  {returned2}")
        for r in rows:
            print(f"  trace={r['trace_id']} task={r['task_number']} "
                  f"dest={r['dest_host']} {r['method']} {r['endpoint']} "
                  f"status={r['status']} latency={r['latency_seconds']:.3f}s "
                  f"bytes_in={r['bytes_in']} bytes_out={r['bytes_out']} "
                  f"cost=${r['cost_dollars']:.4f}")
        traces = {r["trace_id"] for r in rows}
        assert len([r for r in rows if r["trace_id"] == returned1]) == 2
        assert len([r for r in rows if r["trace_id"] == returned2]) == 2
        assert returned1 != returned2 and len(traces) == 2
        print("PASS: each task has exactly 2 attempts under one trace_id; "
              "the two tasks have different trace_ids")
    finally:
        agent_b.shutdown(); proxy.shutdown(); upstream.shutdown()
        proxy.state.conn.close()
        tmp.cleanup()


if __name__ == "__main__":
    main()
