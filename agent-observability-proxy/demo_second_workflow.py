"""Second live workflow: two HTTP legs through Iris, read back Correct.

Proves Iris works on a different destination and method, not just the
first run. First run, Nov 12: CONNECT tunnels. Second run: plain HTTP,
different destination, two legs, two agent steps.

  1. Agent calls A: HTTP GET to destination A, through Iris.
  2. Agent calls B: HTTP POST to destination B, through Iris, small body.

Both legs are read back with the Verify engine (local file read-back)
and must report Correct. A non-allowlisted destination is refused and
journaled: no fail-open. Loopback only. Metadata only. No bodies, no
keys. No scores, no LLM-as-judge.

Run:  python demo_second_workflow.py [--port 8888]
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

# urllib honors NO_PROXY and would bypass the loopback proxy; drop it
# so the run never depends on ambient proxy config.
os.environ.pop("NO_PROXY", None)
os.environ.pop("no_proxy", None)

import db as db_module
import proxy as proxy_module


# Human-approved done clause for this run, once per task type, as a
# named read-back, fixed before the Run starts.
DONE_FILE = {
    "task_type": "local file write",
    "clause": "row exists after close/fsync",
    "read_back": "named read-back: file row exists after close/fsync",
    "approved_by": "human",
}

TRACE = "second-live-workflow-1"


class _LegAHandler(BaseHTTPRequestHandler):
    """Upstream A: logs each GET line to a local file, synced, then 200."""

    out_path = ""

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        with open(self.out_path, "a") as handle:
            handle.write(f"GET {self.path}\n")
            handle.flush()
            os.fsync(handle.fileno())
        body = b"ok-a"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _LegBHandler(BaseHTTPRequestHandler):
    """Upstream B: logs each POST body to a local file, synced, then 200."""

    out_path = ""

    def log_message(self, fmt, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = self.rfile.read(length) if length else b""
        with open(self.out_path, "a") as handle:
            handle.write(payload.decode("utf-8", errors="replace"))
            handle.flush()
            os.fsync(handle.fileno())
        body = b"ok-b"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8888,
                        help="Iris proxy port (loopback only)")
    args = parser.parse_args()

    tmp = tempfile.TemporaryDirectory()
    db_path = os.path.join(tmp.name, "attempts.db")
    file_a = os.path.join(tmp.name, "leg-a.log")
    file_b = os.path.join(tmp.name, "leg-b.log")

    _LegAHandler.out_path = file_a
    _LegBHandler.out_path = file_b
    upstream_a = ThreadingHTTPServer(("127.0.0.1", 0), _LegAHandler)
    threading.Thread(target=upstream_a.serve_forever, daemon=True).start()
    upstream_b = ThreadingHTTPServer(("127.0.0.1", 0), _LegBHandler)
    threading.Thread(target=upstream_b.serve_forever, daemon=True).start()
    port_a = upstream_a.server_address[1]
    port_b = upstream_b.server_address[1]
    assert port_a != port_b, "legs need different destinations"

    try:
        proxy = proxy_module.serve("127.0.0.1", args.port, db_path)
    except OSError:
        print(f"port {args.port} is busy: stop the other Iris first, "
              "or pass --port")
        return 1
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(
        {"http": f"http://127.0.0.1:{proxy.server_address[1]}"}))

    def call(url, data=None):
        req = urllib.request.Request(url, data=data,
                                     method="POST" if data else "GET")
        req.add_header("X-Trace-Id", TRACE)
        try:
            with opener.open(req, timeout=10) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    try:
        # Leg 1: GET to A. Leg 2: POST a small body to B. Both loopback.
        status_a, body_a = call(f"http://127.0.0.1:{port_a}/leg-a")
        print(f"leg A GET /leg-a -> {status_a} {body_a!r}")
        assert status_a == 200, "leg A must flow"
        posted = b"second-live-submit-1"
        status_b, body_b = call(f"http://127.0.0.1:{port_b}/submit",
                                data=posted)
        print(f"leg B POST /submit -> {status_b} {body_b!r}")
        assert status_b == 200, "leg B must flow"

        # No fail-open: a non-allowlisted name is refused, journaled,
        # and the job stays where it was.
        status_x, _ = call("http://exfil.example.test/echo")
        print(f"non-allowlisted exfil attempt -> {status_x}")
        assert status_x == 403, "exfil must be refused at the proxy"

        # Read back both legs with the Verify engine: independent local
        # reads, after close/fsync, not the agent's word. Both must be
        # Correct. Verdicts only, no scores, no judges.
        claim_a = {"kind": "local-file", "path": file_a,
                   "expected_text": "GET /leg-a\n",
                   "idempotency_key": "second-live-leg-a-1"}
        verdict_a, card_a = proxy.state.verify_read_back(
            TRACE, claim_a, done_clause=DONE_FILE)
        print(f"leg A read-back -> {verdict_a}: {card_a['why']}")
        assert verdict_a == "Correct", "leg A must verify Correct"
        claim_b = {"kind": "local-file", "path": file_b,
                   "expected_text": "second-live-submit-1",
                   "idempotency_key": "second-live-leg-b-1"}
        verdict_b, card_b = proxy.state.verify_read_back(
            TRACE, claim_b, done_clause=DONE_FILE)
        print(f"leg B read-back -> {verdict_b}: {card_b['why']}")
        assert verdict_b == "Correct", "leg B must verify Correct"

        # Journal rows: both legs logged, dest_host never empty on
        # traffic rows. Control rows (VERIFY/RETRY/APPROVE) name no
        # destination by design: they are journal bookkeeping, not
        # traffic, and carry the idempotency key in the reason instead.
        conn = db_module.init_db(db_path)
        try:
            rows = conn.execute(
                "SELECT dest_host, endpoint, method, status, http_status,"
                " outcome, reason FROM attempts ORDER BY id").fetchall()
            for row in rows:
                if row[2] not in ("VERIFY", "RETRY", "APPROVE"):
                    assert row[0], f"dest_host must never be empty: {tuple(row)}"
                print(f"row dest={row[0]} endpoint={row[1]} method={row[2]} "
                      f"status={row[3]} http={row[4]} outcome={row[5]} "
                      f"reason={row[6]}")
            outcomes = db_module.fetch_outcome_counts(conn)
            totals = db_module.fetch_totals(conn)
        finally:
            conn.close()
        attempts = totals["attempts"] or 0
        assert sum(outcomes.values()) == attempts, "accounting must reconcile"
        print(f"allowed={outcomes['allowed']} "
              f"blocked={outcomes['blocked']} "
              f"rate_limited={outcomes['rate_limited']} "
              f"paused={outcomes['paused']} "
              f"redirected={outcomes['redirected']} "
              f"stopped={outcomes['stopped']} "
              f"verified={outcomes['verified']} "
              f"other={outcomes['other']}")
        print(f"attempts={attempts} traces={totals['traces'] or 0} "
              f"successes={totals['successes'] or 0} "
              f"cost_dollars={totals['cost_dollars'] or 0:.4f}")
        assert outcomes == {"allowed": 2, "blocked": 1,
                            "rate_limited": 0, "paused": 0,
                            "redirected": 0, "stopped": 0,
                            "verified": 4, "other": 0}, outcomes
        assert totals["cost_dollars"] == 0, "loopback costs $0.00"
        print("PASS: two legs flowed, both read back Correct, exfil "
              "refused at the proxy, accounting reconciles")
        return 0
    finally:
        proxy.shutdown()
        upstream_a.shutdown()
        upstream_b.shutdown()
        proxy.server_close()
        upstream_a.server_close()
        upstream_b.server_close()
        proxy.state.conn.close()
        tmp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
