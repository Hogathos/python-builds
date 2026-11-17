"""Steer per-network override test (test-first, failing until built).

One test only: test_override_pause_cuts_only_that_network.

Problem in one sentence: a human can pause one network without
touching any other network, human-only, journal first, fail-closed.

Gap-fill notes, Charles decision Nov 16 19:53 EST, test only here:
- Gap 1, rate limit: test proxy serves rate_limit=10000, test-only, so
  a 429 never masks the 503 cut refusal. Rate limiting has its own
  tests.
- Gap 2, no round trip first: the override test pauses A immediately
  after open, then asserts the pause row dest_host is the full live
  destination, never ''. This is the register-before-200 gap: the
  registry must be written before the 200 is answered.
- Gap 3, full network key: override is keyed by host + port, never host
  alone, or B (same host, other port) would be cut too.
- Gap 4, Verify gate: a Correct verdict alone never unblocks retry,
  only verify_run stamps permission. Allowed-after-verify_run is a
  later test, named here, not tested here.
- Gap 5, non-allowlisted refusal: refused AND journaled, dest = the
  name as given, outcome blocked, reason non-allowlisted override name.
- Gap 7, registry: after override, no live socket for A remains.
- Gap 8, connections: every DB read closes in finally; temp DB only,
  never the repo attempts.db.
- Gap 9, journal scope: B has no pause row by trace_id AND by
  dest_host; total counts reconcile to total attempts.
- Gap 10, cost: pause row and blocked retry row cost $0.00.
- Gap 12, isolation: fresh proxy + fresh temp DB per test, full
  shutdown in tearDown, so no paused Run leaks into the next test.

Done clause for this test Run (human-approved, once per task type,
as a named read-back, before the Run starts):
  task_type = "local file write"
  clause    = "row exists after close/fsync"
  read_back = "named read-back: file row exists after close/fsync"
No approved done = Unverified, never Correct.

Expected failure right now: set_override does not exist on the proxy
state, so this test FAILS at Step 3. That failure is correct. It is the
test-first proof. Charles reviews this test in Main before any
implementation is written.

Loopback only. Metadata only in journal rows. No bodies, no keys,
no Authorization headers, no real hostnames.
"""
import os
import socket
import socketserver
import sqlite3
import sys
import tempfile
import threading
import time
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


class SteerNetworkOverrideTest(unittest.TestCase):
    """Override pauses one network; the other network still flows."""

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
        # Gap 1: rate limiting has its own tests; this proxy serves a
        # high limit so a 429 never masks the 503 cut refusal below.
        self.proxy = proxy_module.serve(
            "127.0.0.1", 0, self.db_path, rate_limit=10000)
        self.proxy_port = self.proxy.server_address[1]
        threading.Thread(
            target=self.proxy.serve_forever, daemon=True).start()
        # addCleanup runs LIFO: shutdowns are added last so they run
        # first then closes, then DB, then temp. Closing a listening
        # socket while serve_forever still selects on it crashes
        # Windows; shutdown first, always.
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
            return conn.execute(
                "SELECT * FROM attempts ORDER BY id").fetchall()
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

    def test_override_pause_cuts_only_that_network(self):
        """Pause override on net A: A stops, B flows, retry needs Verify."""
        # Step 1: test Run starts WITH a human-approved done clause.
        done = HUMAN_APPROVED_DONE
        self.assertEqual(done["approved_by"], "human")
        self.assertIn("read-back", done["read_back"])
        traceA = "steer-override-run-A"
        traceB = "steer-override-run-B"
        self.assertNotEqual(traceA, traceB)

        # Step 2: two Runs on two loopback destinations, both accepted.
        # Gap 2: no round trip first. The override must journal the live
        # destination straight after open, from the tunnel registry.
        sockA, statusA = self.open_tunnel(self.destA, traceA)
        sockB, statusB = self.open_tunnel(self.destB, traceB)
        self.assertEqual(statusA, 200)
        self.assertEqual(statusB, 200)
        try:
            # Step 3: human sets a pause override on network A only,
            # keyed by full host + port, never host alone (Gap 3), or B
            # on the same host would be cut too. Human-only endpoint,
            # NOT agent-callable (a plain state method, no HTTP route),
            # journal before the override takes effect, fail-closed.
            # EXPECTED FAILURE (test-first): set_override is missing.
            self.assertTrue(
                hasattr(self.proxy.state, "set_override"),
                "Override endpoint does not exist (expected failure, test-first)",
            )
            applied = self.proxy.state.set_override(
                self.destA, "pause", reason="human override")
            self.assertTrue(applied, "set_override refused net A")
            # Gap 5: a non-allowlisted name is refused AND journaled,
            # dest = the name as given, outcome blocked. No live tunnel
            # is cut for it, no pause row either.
            self.assertFalse(
                self.proxy.state.set_override(
                    "exfil.example.test:9999", "pause",
                    reason="human override"),
                "non-allowlisted override must be refused",
            )
            # The refusal names a destination, not a Run: it journals
            # under its own override-attempt trace, exactly one row, and
            # touches no Run's history.
            refused = [
                r for r in self.rows_for(
                    "override::exfil.example.test:9999")
                if r["reason"] == "non-allowlisted override name"
            ]
            self.assertEqual(len(refused), 1,
                             "exactly one row for the refused attempt")
            self.assertEqual(
                refused[0]["dest_host"], "exfil.example.test:9999")
            self.assertEqual(refused[0]["outcome"], "blocked")
            self.assertEqual(refused[-1]["outcome"], "blocked")
            self.assertEqual(
                refused[-1]["dest_host"], "exfil.example.test:9999")
            self.assertEqual(
                [r for r in self.rows_for("exfil.example.test:9999")
                 if r["outcome"] == "paused"],
                [],
                "no pause row for the refused name",
            )

            # Step 4: override cuts only that network. The live tunnel
            # on A is dead, new tunnels to A are refused with 503 (never
            # 429 here: this proxy serves a test-only high rate limit),
            # B still flows after its own round trip.
            self.assert_tunnel_dead(sockA)
            # Gap 7: the registry holds no live socket for A anymore.
            self.assertNotIn(traceA, self.proxy.state._live)
            sockA2, statusA2 = self.open_tunnel(self.destA, traceA)
            sockA2.close()
            self.assertEqual(statusA2, 503, "overridden network stays cut")
            self.assertEqual(
                self.echo_roundtrip(sockB, b"run-still-on-B"),
                b"run-still-on-B",
            )
            pause_rows = [
                r for r in self.rows_for(traceA)
                if r["outcome"] == "paused"
            ]
            self.assertTrue(pause_rows, "override must journal a pause row")
            pause_row = pause_rows[-1]
            self.assertEqual(pause_row["dest_host"], self.destA)
            self.assertEqual(pause_row["reason"], "human override")
            self.assertEqual(
                pause_row["status"], "unknown",
                "override verdict must be Unverified, explicitly")
            # Gap 10: pause rows cost $0.00, never the tunnel's cost.
            self.assertEqual(api_module.attempt_cost(pause_row), 0.0)
            # Gap 9: B has no pause row by trace_id AND by dest_host,
            # and the whole journal reconciles.
            self.assertEqual(
                [r for r in self.rows_for(traceB) if r["outcome"] == "paused"],
                [],
                "other network must have no pause row",
            )
            all_rows = self.rows_all()
            self.assertEqual(
                [r for r in all_rows
                 if r["dest_host"] == self.destB
                 and r["outcome"] == "paused"],
                [],
                "no paused row names B's destination",
            )
            conn = sqlite3.connect(self.db_path)
            try:
                counts = db_module.fetch_outcome_counts(conn)
            finally:
                conn.close()
            total = len(all_rows)
            self.assertEqual(
                counts["allowed"] + counts["blocked"]
                + counts["rate_limited"] + counts["paused"]
                + counts["redirected"] + counts["stopped"]
                + counts["verified"] + counts["other"],
                total)

            # Step 5: Gap 4, Verify gate. A Correct verdict alone never
            # unblocks a retry; only verify_run stamps permission. So a
            # fresh Correct read-back first, then the retry must still be
            # blocked and journaled. (Allowed-after-verify_run is a later
            # test, named here, not tested here: it needs no new gate,
            # the existing Verify gate covers it.)
            proof_path = os.path.join(self.tmp.name, "override-proof.txt")
            with open(proof_path, "w") as proof:
                proof.write("row exists after close/fsync")
                proof.flush()
                os.fsync(proof.fileno())
            verdict, _ = self.proxy.state.verify_read_back(
                traceA,
                {"kind": "local-file", "path": proof_path,
                 "expected_text": "row exists after close/fsync",
                 "idempotency_key": "override-verify-1"},
                done_clause=done)
            self.assertEqual(verdict, "Correct")
            allowed, why = self.proxy.state.retry_run(traceA)
            self.assertFalse(allowed, "retry without Verify must be blocked")
            self.assertIn("verify", why.lower())
            blocked_rows = [
                r for r in self.rows_for(traceA)
                if r["reason"] == "verify required before retry"
            ]
            self.assertTrue(blocked_rows, "blocked retry must be journaled")
            self.assertEqual(api_module.attempt_cost(blocked_rows[-1]), 0.0)
        finally:
            sockA.close()
            sockB.close()


if __name__ == "__main__":
    unittest.main()
