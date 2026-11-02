"""M4 demo: allowlist + rate limit + block test, local traffic only.

Runs upstream + proxy in-process (ephemeral loopback ports, temp DB)
with the visible demo limit of 5 requests per 1s window, then prints
the SQLite report: allowed / blocked / rate_limited counts plus the
usual headline metrics. No real external host is ever contacted: the
blocked destination is a non-allowlisted stand-in name that the proxy
stops before any connection.

Run:  python demo_m4.py
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db as db_module
import proxy as proxy_module
import server as server_module


def main():
    tmp = tempfile.TemporaryDirectory()
    db_path = os.path.join(tmp.name, "attempts.db")
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), server_module.Handler)
    upstream_port = upstream.server_address[1]
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    proxy = proxy_module.serve("127.0.0.1", 0, db_path,
                               rate_limit=5, rate_window=1.0)
    proxy_port = proxy.server_address[1]
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(
        {"http": f"http://127.0.0.1:{proxy_port}"}))
    base = f"http://127.0.0.1:{upstream_port}"

    def call(url, trace, data=None):
        req = urllib.request.Request(url, data=data,
                                     method="POST" if data else "GET")
        req.add_header("X-Trace-Id", trace)
        try:
            with opener.open(req, timeout=10) as resp:
                resp.read()
                return resp.status
        except urllib.error.HTTPError as exc:
            exc.read()
            return exc.code

    try:
        print(f"allowlisted GET /echo -> {call(f'{base}/echo', 'trace-m4-1')}")
        blocked = call("http://exfil.example.test/echo", "trace-m4-blocked",
                       data=b"demo exfil attempt (never forwarded)")
        print(f"non-allowlisted exfil attempt -> {blocked}")
        burst = [call(f"{base}/echo", f"trace-m4-burst-{i}") for i in range(7)]
        print(f"burst of 7 (limit 5/1s) -> {burst}")
        time.sleep(1.2)
        print(f"after pause -> {call(f'{base}/echo', 'trace-m4-after-pause')}")

        conn = db_module.init_db(db_path)
        outcomes = db_module.fetch_outcome_counts(conn)
        totals = db_module.fetch_totals(conn)
        conn.close()
        attempts = totals["attempts"] or 0
        successes = totals["successes"] or 0
        rate = (100.0 * successes / attempts) if attempts else 0.0
        print(f"allowed={outcomes['allowed']} blocked={outcomes['blocked']} "
              f"rate_limited={outcomes['rate_limited']} "
              f"other={outcomes['other']}")
        print(f"attempts={attempts} traces={totals['traces'] or 0} "
              f"successes={successes} success_rate={rate:.1f}% "
              f"retries={totals['retries'] or 0} "
              f"bytes_in={totals['bytes_in'] or 0} "
              f"bytes_out={totals['bytes_out'] or 0} "
              f"cost_dollars={totals['cost_dollars'] or 0:.4f}")
        # The first /echo call also counts toward the same
        # destination window, so the burst forwards 4, not 5.
        assert outcomes == {"allowed": 6, "blocked": 1,
                            "rate_limited": 3, "other": 0}
        print("PASS: allowed forwarded, exfil blocked at proxy, "
              "burst excess rate_limited, recovery after pause")
    finally:
        proxy.shutdown(); upstream.shutdown()
        proxy.state.conn.close()
        tmp.cleanup()


if __name__ == "__main__":
    main()
