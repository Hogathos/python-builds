"""Steer spend caps test (test-first, failing until caps are built).

One test only: test_spend_cap_warns_80_blocks_100.

Problem in one sentence: a human sets a spend cap in dollars for a
Run / network, warn at 80%, block at 100%, journaled, human-only.

Done clause for this test Run (human-approved, once per task type,
as a named read-back, before the Run starts):
  task_type = "local file write"
  clause    = "row exists after close/fsync"
  read_back = "named read-back: file row exists after close/fsync"
No approved done = Unverified, never Correct.

Expected failure right now: set_cap does not exist on the proxy
state, so this test FAILS at Step 2. That failure is correct. It is the
test-first proof. Charles reviews this test in Main before any
implementation is written.

Loopback only. Recorded provider costs are simulated by journaling
rows with cost_dollars, the documented nonzero-cost-wins path; the
enforcement under test is real. No bodies, no keys, no Authorization
headers, no real hostnames. No guessed costs, ever.
"""
import os
import socket
import socketserver
import sqlite3
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# urllib honors NO_PROXY and would bypass the loopback test proxy;
# drop it so the suite never depends on ambient proxy config.
os.environ.pop("NO_PROXY", None)
os.environ.pop("no_proxy", None)

import api as api_module
import db as db_module
import proxy as proxy_module


# Human-approved "done" clause for this test, once per task type,
# as a named read-back, fixed before the Run starts.
HUMAN_APPROVED_DONE = {
    "task_type": "local file write",
    "clause": "row exists after close/fsync",
    "read_back": "named read-back: file row exists after close/fsync",
    "approved_by": "human",
}


class _EchoHandler(socketserver.BaseRequestHandler):
    """Loopback echo upstream. Test helper only, never a real destination."""

    def handle(self):
        while True:
            data = self.request.recv(65536)
            if not data:
                return
            self.request.sendall(data)


class SteerSpendCapTest(unittest.TestCase):
    """Spend cap $1.00: warn at $0.80, block at $1.00, human unblocks."""

    def setUp(self):
        """Fresh proxy, fresh temp DB, two loopback destinations."""
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "attempts.db")
        self.echoA = socketserver.ThreadingTCPServer(
            ("127.0.0.1", 0), _EchoHandler)
        self.echoB = socketserver.ThreadingTCPServer(
            ("127.0.0.1", 0), _EchoHandler)
        threading.Thread(target=self.echoA.serve_forever, daemon=True).start()
        threading.Thread(target=self.echoB.serve_forever, daemon=True).start()
        # Gap: rate limiting has its own tests; this proxy serves a high
        # limit so a 429 never masks the 503 cut refusal checked below.
        self.proxy = proxy_module.serve(
            "127.0.0.1", 0, self.db_path, rate_limit=10000)
        self.proxy_port = self.proxy.server_address[1]
        threading.Thread(
            target=self.proxy.serve_forever, daemon=True).start()
        # addCleanup runs LIFO: shutdowns first, then closes, then DB,
        # then temp. Closing a listening socket while serve_forever
        # still selects on it crashes Windows; shutdown first, always.
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.proxy.state.conn.close)
        self.addCleanup(self.echoA.server_close)
        self.addCleanup(self.echoB.server_close)
        self.addCleanup(self.proxy.server_close)
        self.addCleanup(self.echoA.shutdown)
        self.addCleanup(self.echoB.shutdown)
        self.addCleanup(self.proxy.shutdown)
        self.destA = f"127.0.0.1:{self.echoA.server_address[1]}"
        self.destB = f"127.0.0.1:{self.echoB.server_address[1]}"
        assert self.destA != self.destB

    def rows_for(self, trace_id):
        """All journal rows for one trace_id, oldest first. Read only."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            return conn.execute(
                "SELECT * FROM attempts WHERE trace_id = ? ORDER BY id",
                (trace_id,)).fetchall()
        finally:
            conn.close()

    def rows_all(self):
        """Every journal row, oldest first. Read only, closes in finally."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            return conn.execute("SELECT * FROM attempts ORDER BY id").fetchall()
        finally:
            conn.close()

    def open_tunnel(self, dest, trace_id):
        """Open one raw CONNECT tunnel; return (socket, status code)."""
        sock = socket.create_connection(
            ("127.0.0.1", self.proxy_port), timeout=5)
        sock.settimeout(5)
        sock.sendall(
            (
                f"CONNECT {dest} HTTP/1.1\r\n"
                f"Host: {dest}\r\n"
                f"X-Trace-Id: {trace_id}\r\n"
                "\r\n"
            ).encode()
        )
        raw = b""
        while b"\r\n\r\n" not in raw:
            chunk = sock.recv(65536)
            self.assertTrue(chunk, "proxy never answered CONNECT")
            raw += chunk
        head = raw.split(b"\r\n\r\n", 1)[0].decode(errors="replace")
        return sock, int(head.split()[1])

    def echo_roundtrip(self, sock, payload):
        """Send bytes through a tunnel, expect the same bytes back."""
        sock.sendall(payload)
        got = b""
        while len(got) < len(payload):
            chunk = sock.recv(65536)
            if not chunk:
                break
            got += chunk
        return got

    def assert_tunnel_dead(self, sock):
        """A cut tunnel carries no more bytes: EOF or error, never an echo."""
        sock.settimeout(5)
        try:
            sock.sendall(b"ping-after-cut")
        except socket.timeout:
            self.fail("tunnel send timed out: cut did not take effect")
        except OSError:
            return
        try:
            data = sock.recv(65536)
        except socket.timeout:
            self.fail("tunnel recv timed out: cut did not take effect")
        except OSError:
            return
        self.assertEqual(data, b"", "tunnel still flows after cut")

    def record_cost(self, trace_id, dest, dollars):
        """Simulate one provider-reported cost row. The nonzero-cost-wins
        path is documented schema behavior; enforcement is under test."""
        conn = sqlite3.connect(self.db_path)
        try:
            db_module.log_attempt(
                conn, trace_id=trace_id, task_number=1, attempt=1,
                status="success", dest_host=dest, endpoint=dest,
                method="CONNECT", http_status=200, outcome="allowed",
                cost_dollars=dollars)
        finally:
            conn.close()

    def record_unpriced(self, trace_id, dest):
        """Simulate one allowed row with no priced cost: Unverified spend
        that must never count toward a cap, and must never be guessed."""
        conn = sqlite3.connect(self.db_path)
        try:
            db_module.log_attempt(
                conn, trace_id=trace_id, task_number=1, attempt=1,
                status="success", dest_host=dest, endpoint=dest,
                method="CONNECT", http_status=200, outcome="allowed",
                cost_dollars=0.0)
        finally:
            conn.close()

    def test_spend_cap_warns_80_blocks_100(self):
        """Cap $1.00 on net A: warn at $0.80, block at $1.00, B flows."""
        # Step 1: Run starts WITH a human-approved done clause, and a
        # human sets a $1.00 cap on network A only, host + port, never
        # host alone. Human-only endpoint, NOT agent-callable (a plain
        # state method, no HTTP route), journal first, cap persisted.
        # EXPECTED FAILURE (test-first): set_cap is missing.
        done = HUMAN_APPROVED_DONE
        self.assertEqual(done["approved_by"], "human")
        self.assertIn("read-back", done["read_back"])
        traceA = "steer-spendcap-run-A"
        traceB = "steer-spendcap-run-B"
        self.assertNotEqual(traceA, traceB)
        self.assertTrue(
            hasattr(self.proxy.state, "set_cap"),
            "Cap endpoint does not exist (expected failure, test-first)",
        )
        self.assertTrue(
            self.proxy.state.set_cap(self.destA, 1.00, reason="human cap"),
            "set_cap refused net A",
        )
        set_rows = [
            r for r in self.rows_for(traceA)
            if r["reason"] == "cap set $1.00"
        ] + [
            r for r in self.rows_all()
            if r["reason"] == "cap set $1.00"
        ]
        self.assertTrue(set_rows, "cap set must be journaled")

        # Step 2: recorded cost reaches $0.80. Warn row, outcome warned,
        # cost $0.80, run continues, next call flows.
        sockA, statusA = self.open_tunnel(self.destA, traceA)
        self.assertEqual(statusA, 200)
        sockB, statusB = self.open_tunnel(self.destB, traceB)
        self.assertEqual(statusB, 200)
        try:
            for _ in range(4):
                self.record_cost(traceA, self.destA, 0.20)
            probe, probe_status = self.open_tunnel(self.destA, traceA)
            probe.close()
            self.assertEqual(probe_status, 200, "warn must not stop the run")
            warn_rows = [
                r for r in self.rows_for(traceA)
                if r["outcome"] == "warned"
            ]
            self.assertTrue(warn_rows, "80% must journal a warn row")
            self.assertEqual(warn_rows[-1]["reason"], "cap warn 80%")
            self.assertEqual(api_module.attempt_cost(warn_rows[-1]), 0.80)
            self.assertEqual(
                self.echo_roundtrip(sockB, b"run-still-on-B"),
                b"run-still-on-B",
            )

            # Step 3: recorded cost reaches $1.00. The next request
            # trips the gate: block row, outcome blocked, cost $0.00 for
            # the blocked row, live tunnels cut, new tunnels refused,
            # retry blocked and journaled. Enforcement happens on the
            # request path, so the probe that trips it comes first, and
            # the dead-tunnel assert follows the cut it caused.
            self.record_cost(traceA, self.destA, 0.20)
            sockA2, statusA2 = self.open_tunnel(self.destA, traceA)
            sockA2.close()
            self.assertEqual(statusA2, 503, "capped network stays cut")
            self.assert_tunnel_dead(sockA)
            blocked_rows = [
                r for r in self.rows_for(traceA)
                if r["outcome"] == "blocked"
            ]
            self.assertTrue(blocked_rows, "100% must journal a block row")
            self.assertEqual(blocked_rows[-1]["reason"], "cap block 100%")
            self.assertEqual(api_module.attempt_cost(blocked_rows[-1]), 0.0)
            allowed, why = self.proxy.state.retry_run(traceA)
            self.assertFalse(allowed, "retry without Verify must be blocked")
            self.assertIn("verify", why.lower())
            self.assertTrue(
                [r for r in self.rows_for(traceA)
                 if r["reason"] == "verify required before retry"],
                "blocked retry must be journaled",
            )

            # Step 4: retry after block, with a Correct verdict alone and
            # no verify_run, stays blocked and journaled. Only verify_run
            # stamps permission; the verdict never does.
            proof_path = os.path.join(self.tmp.name, "spend-proof.txt")
            with open(proof_path, "w") as proof:
                proof.write("row exists after close/fsync")
                proof.flush()
                os.fsync(proof.fileno())
            with open(proof_path) as proof:
                self.assertEqual(proof.read(), "row exists after close/fsync")
            verdict, _ = self.proxy.state.verify_read_back(
                traceA,
                {"kind": "local-file", "path": proof_path,
                 "expected_text": "row exists after close/fsync",
                 "idempotency_key": "spend-verify-1"},
                done_clause=done)
            self.assertEqual(verdict, "Correct")
            allowed, _ = self.proxy.state.retry_run(traceA)
            self.assertFalse(allowed, "Correct alone never unblocks a retry")
            self.assertTrue(
                [r for r in self.rows_for(traceA)
                 if r["reason"] == "verify required before retry"],
                "still-blocked retry must be journaled",
            )

            # Step 5: human-only unblock, after Verify. The run can
            # retry, and the unblock is journaled.
            self.assertTrue(
                self.proxy.state.verify_run(traceA, done_clause=done),
                "fresh Verify must pass",
            )
            self.assertTrue(
                self.proxy.state.unblock_cap(self.destA, reason="human unblock"),
                "human unblock must be accepted",
            )
            unblock_rows = [
                r for r in self.rows_all()
                if r["reason"] == "cap lifted"
            ]
            self.assertTrue(unblock_rows, "unblock must be journaled")
            allowed, _ = self.proxy.state.retry_run(traceA)
            self.assertTrue(allowed, "retry after unblock must be allowed")

            # Step 6: cost rules, never guessed. Blocked, rate_limited,
            # paused, redirected, stopped, verified always $0.00, nonzero
            # recorded cost wins, loopback $0.00, else Unverified. Pause
            # and blocked rows here cost $0.00. Unverified costs never
            # count: an unpriced row contributes nothing, and nothing is
            # guessed in its place.
            for row in self.rows_all():
                cost = api_module.attempt_cost(row)
                if row["outcome"] in ("blocked", "rate_limited", "paused",
                                      "redirected", "stopped", "verified"):
                    self.assertEqual(cost, 0.0)
                elif row["cost_dollars"]:
                    self.assertEqual(cost, row["cost_dollars"])
            self.record_unpriced(traceB, "pay.example.com:443")
            self.assertEqual(
                self.proxy.state.capped_total("pay.example.com:443"), 0)
            # Zero-cost activity triggers nothing: cap B at $1.00 with
            # only $0.00 rows, and no warn or block row may appear.
            self.assertTrue(
                self.proxy.state.set_cap(self.destB, 1.00, reason="human cap"))
            probeB, statusB = self.open_tunnel(self.destB, traceB)
            probeB.close()
            self.assertEqual(statusB, 200)
            self.assertEqual(
                [r for r in self.rows_for(traceB)
                 if r["outcome"] in ("warned", "blocked")],
                [],
                "no cost, no warn, no block: never guessed",
            )

            # Step 7: cap is per Run / network, host + port, not host
            # only. A cap on A does NOT block B, B still flows, B has no
            # warn / block row.
            self.assertEqual(
                self.echo_roundtrip(sockB, b"run-B-unaffected"),
                b"run-B-unaffected",
            )
            self.assertEqual(
                [r for r in self.rows_for(traceB)
                 if r["outcome"] in ("warned", "blocked")],
                [],
                "cap on A must not touch B",
            )

            # Accounting reconciles across every outcome, including the
            # new warned outcome: total always equals the row count.
            conn = sqlite3.connect(self.db_path)
            try:
                counts = db_module.fetch_outcome_counts(conn)
            finally:
                conn.close()
            all_rows = self.rows_all()
            self.assertEqual(
                counts["allowed"] + counts["blocked"]
                + counts["rate_limited"] + counts["paused"]
                + counts["redirected"] + counts["stopped"]
                + counts["verified"] + counts["warned"]
                + counts["other"],
                len(all_rows))
        finally:
            sockA.close()
            sockB.close()


if __name__ == "__main__":
    unittest.main()
