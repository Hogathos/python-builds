"""Devtool WARNED / BLOCKED states test (test-first, failing until built).

One test only: test_warn_block_states_pause_button.

Problem in one sentence: the panel state machine is missing WARNED
and BLOCKED, so a capped run reads wrong and the Pause button cannot
explain itself on those states.

Expected failure right now: devpanel.states does not exist, so this
test FAILS at import. That failure is correct. It is the test-first
proof. Charles reviews this test in Main before any implementation is
written.

Done clause for this test Run (human-approved, once per task type,
as a named read-back, before the Run starts):
  task_type = "local file write"
  clause    = "row exists after close/fsync"
  read_back = "named read-back: file row exists after close/fsync"
No approved done = Unverified, never Correct.

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
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# urllib honors NO_PROXY and would bypass the loopback test proxy;
# drop it so the suite never depends on ambient proxy config.
os.environ.pop("NO_PROXY", None)
os.environ.pop("no_proxy", None)

import api as api_module
import api as api_module
import db as db_module
import proxy as proxy_module
from devpanel import states as states_module


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


class DevtoolStatesWarnBlockTest(unittest.TestCase):
    """WARNED at 80%: Pause stays live. BLOCKED at 100%: stop, then unblock."""

    def setUp(self):
        """Fresh proxy, fresh temp DB, two loopback destinations, no cap."""
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "attempts.db")
        self.echoA = socketserver.ThreadingTCPServer(
            ("127.0.0.1", 0), _EchoHandler)
        self.echoB = socketserver.ThreadingTCPServer(
            ("127.0.0.1", 0), _EchoHandler)
        threading.Thread(target=self.echoA.serve_forever, daemon=True).start()
        threading.Thread(target=self.echoB.serve_forever, daemon=True).start()
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
            return [dict(r) for r in conn.execute(
                "SELECT * FROM attempts WHERE trace_id = ? ORDER BY id",
                (trace_id,)).fetchall()]
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

    def record_cost(self, trace_id, dest_host, dollars):
        """Simulate one provider-reported cost row. Read-only test helper:
        the nonzero-cost-wins path is documented schema behavior."""
        conn = sqlite3.connect(self.db_path)
        try:
            db_module.log_attempt(
                conn, trace_id=trace_id, task_number=1, attempt=1,
                status="success", dest_host=dest_host, endpoint=dest_host,
                method="CONNECT", http_status=200, outcome="allowed",
                cost_dollars=dollars)
        finally:
            conn.close()

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

    def test_warn_block_states_pause_button(self):
        """WARNED keeps Pause live; BLOCKED explains itself, then unblocks."""
        # Step 1: test Run starts WITH a human-approved done clause.
        done = HUMAN_APPROVED_DONE
        self.assertEqual(done["approved_by"], "human")
        self.assertIn("read-back", done["read_back"])
        traceA = "devtool-warnblock-A"
        traceB = "devtool-warnblock-B"
        self.assertNotEqual(traceA, traceB)
        self.assertTrue(
            self.proxy.state.set_cap(self.destA, 1.00, reason="human cap"),
            "set_cap refused net A",
        )

        # Step 2: spend reaches 80%. A warn row is journaled, the run
        # continues, the state machine reads WARNED, and the Pause
        # button stays live with its WARNED words.
        sockA = self.open_tunnel(self.destA, traceA)[0]
        sockB = self.open_tunnel(self.destB, traceB)[0]
        try:
            for _ in range(4):
                self.record_cost(traceA, self.destA, 0.20)
            probe, probe_status = self.open_tunnel(self.destA, traceA)
            probe.close()
            self.assertEqual(probe_status, 200, "warn must not stop the run")
            rowsA = self.rows_for(traceA)
            self.assertEqual(
                states_module.run_state(rowsA), "WARNED",
                "80% spend must read WARNED")
            self.assertEqual(
                states_module.verdict_for(rowsA), "Unverified")
            live, why = states_module.pause_button_live("WARNED")
            self.assertTrue(live, "Pause must stay live in WARNED")
            self.assertEqual(
                why, "Money spent at 80% of cap, run continues")
            self.assertEqual(
                self.echo_roundtrip(sockB, b"run-B-unaffected"),
                b"run-B-unaffected")

            # Step 3: spend reaches 100%. A block row is journaled, the
            # live tunnel is cut with no data after the block, new
            # tunnels are refused with 503, and the state machine reads
            # BLOCKED with the Pause button explaining itself.
            self.record_cost(traceA, self.destA, 0.20)
            sockA2, statusA2 = self.open_tunnel(self.destA, traceA)
            sockA2.close()
            self.assertEqual(statusA2, 503, "capped network stays cut")
            self.assert_tunnel_dead(sockA)
            rowsA = self.rows_for(traceA)
            self.assertEqual(
                states_module.run_state(rowsA), "BLOCKED",
                "100% spend must read BLOCKED")
            live, why = states_module.pause_button_live("BLOCKED")
            self.assertFalse(live, "Pause must rest in BLOCKED")
            self.assertEqual(
                why,
                "Blocked at 100% of cap, a human must check it again, "
                "then unblock after Verify")

            # Step 4: retry without a fresh Verify stays blocked and
            # journaled, even after a Correct read-back on its own.
            path = os.path.join(self.tmp.name, "wb-proof.txt")
            with open(path, "w") as proof:
                proof.write("row exists after close/fsync")
                proof.flush()
                os.fsync(proof.fileno())
            verdict, _ = self.proxy.state.verify_read_back(
                traceA,
                {"kind": "local-file", "path": path,
                 "expected_text": "row exists after close/fsync",
                 "idempotency_key": "wb-verify-1"},
                done_clause=done)
            self.assertEqual(verdict, "Correct")
            allowed, why = self.proxy.state.retry_run(traceA)
            self.assertFalse(allowed, "Correct alone never unblocks")
            self.assertIn("verify", why.lower())
            self.assertTrue(
                [r for r in self.rows_for(traceA)
                 if r["reason"] == "verify required before retry"],
                "still-blocked retry must be journaled")

            # Step 5: human unblock after Verify. The lift is journaled,
            # the state machine reads FLOWING again, and a new tunnel
            # flows. No new outcome was invented for any of this.
            self.assertTrue(
                self.proxy.state.verify_run(traceA, done_clause=done),
                "fresh Verify must pass")
            self.assertTrue(
                self.proxy.state.unblock_cap(
                    self.destA, reason="human unblock"),
                "human unblock must be accepted")
            self.assertTrue(
                [r for r in self.rows_all()
                 if r["reason"] == "cap lifted"],
                "unblock must be journaled")
            allowed, _ = self.proxy.state.retry_run(traceA)
            self.assertTrue(allowed, "retry after unblock must be allowed")
            sockA3, statusA3 = self.open_tunnel(self.destA, traceA)
            try:
                self.assertEqual(statusA3, 200, "unblocked run flows")
            finally:
                sockA3.close()
            self.assertEqual(
                states_module.run_state(self.rows_for(traceA)), "FLOWING")

            # Step 6: accounting reconciles across every outcome,
            # including warned. Warned rows keep what was spent.
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
            for row in all_rows:
                if row["outcome"] == "warned":
                    self.assertEqual(api_module.attempt_cost(row), 0.80)
                if row["outcome"] == "blocked":
                    self.assertEqual(api_module.attempt_cost(row), 0.0)
        finally:
            sockA.close()
            sockB.close()

    def rows_all(self):
        """Every journal row, oldest first. Read only, closes in finally."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(
                "SELECT * FROM attempts ORDER BY id").fetchall()]
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
