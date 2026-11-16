"""Steer Redirect-one-Run test (test-first: failed until Redirect was built).

One test only: test_redirect_one_run_moves_only_that_run.

Problem in one sentence: Redirect one Run must move a Run to a
different loopback destination, human-only, journal first, without
touching any other Run.

Done clause for this test Run (human-approved, once per task type,
as a named read-back, before the Run starts):
  task_type = "local file write"
  clause    = "row exists after close/fsync"
  read_back = "named read-back: file row exists after close/fsync"
No approved done = Unverified, never Correct.

Expected failure right now: redirect_run does not exist on the proxy
state, so this test FAILED at Step 3. That failure was the correct
test-first proof. Charles approved the test in Main, then Redirect was
implemented. The test now proves the behavior.

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

import proxy as proxy_module


# Human-approved "done" clause for this test Run, once per task type,
# as a named read-back, fixed before the Run starts.
HUMAN_APPROVED_DONE = {
    "task_type": "local file write",
    "clause": "row exists after close/fsync",
    "read_back": "named read-back: file row exists after close/fsync",
    "approved_by": "human",
}


class _CountingEchoHandler(socketserver.BaseRequestHandler):
    """Loopback echo upstream that counts its own connections.

    The count proves which destination a tunnel really reached, so
    Step 4 can tell C apart from A without reading any byte content.
    """

    def handle(self):
        self.server.count += 1
        while True:
            data = self.request.recv(65536)
            if not data:
                return
            self.request.sendall(data)


class SteerRedirectOneRunTest(unittest.TestCase):
    """Redirect one Run from destination A to destination C, only that Run."""

    @classmethod
    def setUpClass(cls):
        """Start three loopback destinations A, B, C and one proxy."""
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.tmp.name, "attempts.db")
        cls.echoA = socketserver.ThreadingTCPServer(
            ("127.0.0.1", 0), _CountingEchoHandler)
        cls.echoA.count = 0
        threading.Thread(target=cls.echoA.serve_forever, daemon=True).start()
        cls.echoB = socketserver.ThreadingTCPServer(
            ("127.0.0.1", 0), _CountingEchoHandler)
        cls.echoB.count = 0
        threading.Thread(target=cls.echoB.serve_forever, daemon=True).start()
        cls.echoC = socketserver.ThreadingTCPServer(
            ("127.0.0.1", 0), _CountingEchoHandler)
        cls.echoC.count = 0
        threading.Thread(target=cls.echoC.serve_forever, daemon=True).start()
        cls.proxy = proxy_module.serve("127.0.0.1", 0, cls.db_path)
        cls.proxy_port = cls.proxy.server_address[1]
        threading.Thread(target=cls.proxy.serve_forever, daemon=True).start()
        cls.destA = f"127.0.0.1:{cls.echoA.server_address[1]}"
        cls.destB = f"127.0.0.1:{cls.echoB.server_address[1]}"
        cls.destC = f"127.0.0.1:{cls.echoC.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        """Shut down proxy, echoes, and temp db. No files left behind."""
        cls.proxy.shutdown()
        cls.echoA.shutdown()
        cls.echoB.shutdown()
        cls.echoC.shutdown()
        cls.proxy.server_close()
        cls.echoA.server_close()
        cls.echoB.server_close()
        cls.echoC.server_close()
        cls.proxy.state.conn.close()
        cls.tmp.cleanup()

    def rows_for(self, trace_id):
        """All journal rows for one trace_id, oldest first. Read only."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(
                "SELECT * FROM attempts WHERE trace_id = ? ORDER BY id",
                (trace_id,),
            ).fetchall()
        finally:
            conn.close()

    def open_tunnel(self, dest, trace_id):
        """Open one raw CONNECT tunnel through the proxy. Loopback only."""
        sock = socket.create_connection(("127.0.0.1", self.proxy_port), timeout=5)
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
        self.assertEqual(int(head.split()[1]), 200, f"CONNECT refused: {head}")
        return sock

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

    def wait_row(self, trace_id, predicate, what):
        """Poll the journal briefly for a row the proxy writes async."""
        deadline = time.time() + 5.0
        while time.time() < deadline:
            found = [r for r in self.rows_for(trace_id) if predicate(r)]
            if found:
                return found[-1]
            time.sleep(0.05)
        self.fail(f"no journal row for {what} (trace {trace_id})")

    def test_redirect_one_run_moves_only_that_run(self):
        """Redirect Run 1 A->C; Run 2 stays on B; Verify gates the retry."""
        # Step 1: test Run 1 starts WITH a human-approved done clause.
        # Without this clause the Run verdict could never be Correct.
        done = HUMAN_APPROVED_DONE
        self.assertEqual(done["approved_by"], "human")
        self.assertIn("read-back", done["read_back"])
        trace1 = "steer-redirect-test-run-1"
        trace2 = "steer-redirect-test-run-2"
        self.assertNotEqual(trace1, trace2)

        # Step 2: second test Run, different trace_id, different
        # loopback destination B. A, B, C are all 127.0.0.1.
        sock1 = self.open_tunnel(self.destA, trace1)
        sock2 = self.open_tunnel(self.destB, trace2)
        try:
            self.assertEqual(self.echo_roundtrip(sock1, b"run1-on-A"), b"run1-on-A")
            self.assertEqual(self.echo_roundtrip(sock2, b"run2-on-B"), b"run2-on-B")
            self.assertEqual(self.echoA.count, 1)
            self.assertEqual(self.echoB.count, 1)
            self.assertEqual(self.echoC.count, 0)

            # Step 3: Redirect Run 1 only, A to C. Human-only endpoint,
            # NOT agent-callable (a plain state method, no HTTP route, so
            # proxied traffic cannot call it), local-first, fail-closed.
            # Journal BEFORE the redirect takes effect: state save plus
            # journal commit first, socket and tunnel change after.
            # Test-first history: this failed here before Redirect
            # existed. Charles approved the test, then it was built.
            self.assertTrue(
                hasattr(self.proxy.state, "redirect_run"),
                "Redirect endpoint does not exist",
            )
            moved = self.proxy.state.redirect_run(
                trace1, self.destC, reason="human redirect")
            self.assertTrue(moved, "redirect_run refused Run 1 to C")

            # Step 4: Run 1 traffic now goes to C, not A. The old tunnel
            # is cut, the redirect is journaled with outcome redirected,
            # reason human redirect, verdict Unverified explicitly:
            # status unknown, never Correct, never Incorrect. C is
            # allowlisted loopback; the count proves where bytes went.
            with self.assertRaises((OSError, socket.timeout)):
                sock1.settimeout(2)
                sock1.sendall(b"run1-after-redirect")
                self.assertEqual(
                    self.echo_roundtrip(sock1, b"run1-after-redirect"), b"")
            redirect_rows = [
                r for r in self.rows_for(trace1)
                if r["outcome"] == "redirected"
            ]
            self.assertTrue(redirect_rows, "no outcome=redirected row for Run 1")
            # The control row names the new destination; the cut row for
            # the old tunnel carries the old one. Both are redirected.
            redirect_row = None
            for r in redirect_rows:
                if r["dest_host"] == self.destC:
                    redirect_row = r
            self.assertTrue(redirect_row, "no redirect row naming C for Run 1")
            self.assertEqual(redirect_row["trace_id"], trace1)
            self.assertEqual(redirect_row["reason"], "human redirect")
            self.assertTrue(redirect_row["created_at"], "redirect needs a timestamp")
            # Unverified, explicitly: a redirect alone verifies nothing,
            # so the verdict must read Unknown, never Correct and never
            # Incorrect. Unknown is the explicit state, not a guess.
            self.assertEqual(
                redirect_row["status"], "unknown",
                "redirect verdict must be Unverified, explicitly")
            row_text = " ".join(
                str(redirect_row[k]) for k in redirect_row.keys())
            self.assertNotIn("Authorization", row_text)
            self.assertNotIn("Bearer", row_text)
            # New tunnels for Run 1, asked for A, land on C instead.
            a_before, c_before = self.echoA.count, self.echoC.count
            sock1_new = self.open_tunnel(self.destA, trace1)
            try:
                self.assertEqual(
                    self.echo_roundtrip(sock1_new, b"run1-on-C"), b"run1-on-C")
                self.assertEqual(self.echoA.count, a_before, "nothing new reached A")
                self.assertEqual(self.echoC.count, c_before + 1, "one tunnel reached C")
            finally:
                sock1_new.close()
            landed = self.wait_row(
                trace1, lambda r: r["dest_host"] == self.destC,
                "tunnel row on C")
            self.assertEqual(landed["dest_host"], self.destC)

            # Step 5: Run 2 still flows to B, unchanged, and has no
            # redirect row. Redirect touched one trace_id only.
            self.assertEqual(self.echo_roundtrip(sock2, b"run2-still-B"), b"run2-still-B")
            self.assertEqual(
                [r for r in self.rows_for(trace2) if r["outcome"] == "redirected"],
                [],
                "Run 2 must have no redirect row",
            )

            # Step 6: redirect to a non-allowlisted destination is
            # refused and journaled. Run 1 stays where it was (on C,
            # still unverified), nothing fails open to the new name.
            refused = self.proxy.state.redirect_run(
                trace1, "exfil.example.test:9999", reason="human redirect")
            self.assertFalse(refused, "non-allowlisted redirect must be refused")
            refused_rows = [
                r for r in self.rows_for(trace1)
                if r["reason"] == "redirect refused: not allowlisted"
            ]
            self.assertTrue(refused_rows, "refused redirect must be journaled")
            self.assertEqual(refused_rows[-1]["status"], "unknown")
            a_before, c_before = self.echoA.count, self.echoC.count
            sock1_check = self.open_tunnel(self.destA, trace1)
            try:
                self.assertEqual(
                    self.echo_roundtrip(sock1_check, b"run1-still-C"),
                    b"run1-still-C")
                self.assertEqual(self.echoA.count, a_before, "nothing new reached A")
                self.assertEqual(self.echoC.count, c_before + 1, "Run 1 stays on C")
            finally:
                sock1_check.close()

            # Step 7: after a fresh Verify, Run 1 on C is allowed and
            # journaled; a retry on C without Verify is blocked and
            # journaled. The named read-back is executed here: written,
            # synced, read back. That read could have failed (missing
            # file, short read); only then does the Verify count.
            allowed, why = self.proxy.state.retry_run(trace1)
            self.assertFalse(allowed, "retry on C without Verify must be blocked")
            self.assertIn("verify", why.lower())
            self.assertTrue(
                [r for r in self.rows_for(trace1)
                 if r["reason"] == "verify required before retry"],
                "blocked retry must be journaled",
            )
            proof_path = os.path.join(self.tmp.name, "redirect-done-proof.txt")
            with open(proof_path, "w") as proof:
                proof.write("row exists after close/fsync")
                proof.flush()
                os.fsync(proof.fileno())
            with open(proof_path) as proof:
                self.assertEqual(proof.read(), "row exists after close/fsync")
            verified = self.proxy.state.verify_run(trace1, done_clause=done)
            self.assertTrue(verified, "fresh Verify must pass")
            self.assertTrue(
                [r for r in self.rows_for(trace1)
                 if r["reason"] == "verify ok"],
                "fresh Verify must be journaled",
            )
            allowed, _ = self.proxy.state.retry_run(trace1)
            self.assertTrue(allowed, "retry on C after fresh Verify must be allowed")
            self.assertTrue(
                [r for r in self.rows_for(trace1)
                 if r["reason"] == "retry allowed after verify"],
                "allowed retry must be journaled",
            )
        finally:
            sock1.close()
            sock2.close()


if __name__ == "__main__":
    unittest.main()
