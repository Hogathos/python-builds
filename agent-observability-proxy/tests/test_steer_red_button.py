"""Steer Red-button test (test-first: failed until Red button was built).

One test only: test_red_button_stops_all_runs.

Problem in one sentence: Red button must stop all agent jobs at once,
human-only, journal first, fail-closed, without touching the journal,
and without letting any Run keep working.

Plain words, for evaluators: Red button means stop all agent jobs
at once.

Done clause for this test Run (human-approved, once per task type,
as a named read-back, before the Run starts):
  task_type = "local file write"
  clause    = "row exists after close/fsync"
  read_back = "named read-back: file row exists after close/fsync"
No approved done = Unverified, never Correct.

Test-first history: this test FAILED at Step 4 before Red button
existed, and that failure was the correct proof. Charles approved the
test in Main, then Red button was implemented. The test now proves the
behavior.

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


# Human-approved "done" clause for this test, once per task type,
# as a named read-back, fixed before the Run starts.
HUMAN_APPROVED_DONE = {
    "task_type": "local file write",
    "clause": "row exists after close/fsync",
    "read_back": "named read-back: file row exists after close/fsync",
    "approved_by": "human",
}


class _CountingEchoHandler(socketserver.BaseRequestHandler):
    """Loopback echo upstream that counts its own connections.

    The count proves whether a tunnel really reached a destination,
    so a refused Run shows zero new connections without reading bytes.
    """

    def handle(self):
        self.server.count += 1
        while True:
            data = self.request.recv(65536)
            if not data:
                return
            self.request.sendall(data)


class SteerRedButtonTest(unittest.TestCase):
    """Red button stops every Run at once, and nothing restarts alone."""

    @classmethod
    def setUpClass(cls):
        """Start four loopback destinations and one proxy on temp db."""
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.tmp.name, "attempts.db")
        cls.echoes = []
        for _ in range(4):
            echo = socketserver.ThreadingTCPServer(
                ("127.0.0.1", 0), _CountingEchoHandler)
            echo.count = 0
            threading.Thread(target=echo.serve_forever, daemon=True).start()
            cls.echoes.append(echo)
        cls.proxy = proxy_module.serve("127.0.0.1", 0, cls.db_path)
        cls.proxy_port = cls.proxy.server_address[1]
        threading.Thread(target=cls.proxy.serve_forever, daemon=True).start()
        cls.destA = f"127.0.0.1:{cls.echoes[0].server_address[1]}"
        cls.destB = f"127.0.0.1:{cls.echoes[1].server_address[1]}"
        cls.destC = f"127.0.0.1:{cls.echoes[2].server_address[1]}"
        cls.destD = f"127.0.0.1:{cls.echoes[3].server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        """Shut down proxy, echoes, and temp db. No files left behind."""
        cls.proxy.shutdown()
        for echo in cls.echoes:
            echo.shutdown()
        cls.proxy.server_close()
        for echo in cls.echoes:
            echo.server_close()
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

    def connect_status(self, dest, trace_id):
        """Open one raw CONNECT tunnel; return (socket, status code)."""
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
        return sock, int(head.split()[1])

    def open_tunnel(self, dest, trace_id):
        """Open one CONNECT tunnel that must be accepted. Loopback only."""
        sock, status = self.connect_status(dest, trace_id)
        self.assertEqual(status, 200, f"CONNECT refused: {status}")
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

    def test_red_button_stops_all_runs(self):
        """Red button cuts every tunnel; only fresh approval restarts."""
        # Step 1: test Run 1 starts WITH a human-approved done clause.
        # Without this clause the Run verdict could never be Correct.
        done = HUMAN_APPROVED_DONE
        self.assertEqual(done["approved_by"], "human")
        self.assertIn("read-back", done["read_back"])
        trace1 = "steer-redbutton-run-1"
        trace2 = "steer-redbutton-run-2"
        trace3 = "steer-redbutton-run-3"
        trace4 = "steer-redbutton-run-4"
        self.assertEqual(len({trace1, trace2, trace3, trace4}), 4)

        # Step 2: second Run, different trace_id, different loopback
        # destination B. A, B, C, D are all 127.0.0.1.
        sock1 = self.open_tunnel(self.destA, trace1)
        sock2 = self.open_tunnel(self.destB, trace2)
        try:
            self.assertEqual(self.echo_roundtrip(sock1, b"run1-on-A"), b"run1-on-A")
            self.assertEqual(self.echo_roundtrip(sock2, b"run2-on-B"), b"run2-on-B")

            # Step 3: third Run on C, already paused. Red button must
            # stop a paused Run too, not just a flowing one.
            sock3 = self.open_tunnel(self.destC, trace3)
            try:
                self.assertEqual(
                    self.echo_roundtrip(sock3, b"run3-on-C"), b"run3-on-C")
                self.assertTrue(
                    self.proxy.state.pause_run(trace3, reason="human pause"))
                stopped3_before = [
                    r for r in self.rows_for(trace3)
                    if r["outcome"] == "stopped"
                ]
                self.assertEqual(stopped3_before, [], "no stop row before Red button")
            finally:
                sock3.close()

            # Step 4: Red button. Human-only endpoint, NOT agent-callable
            # (a plain state method, no HTTP route, so proxied traffic
            # cannot call it), local-first, fail-closed. Journal row
            # first, then stop all: state save plus journal commit, then
            # every tunnel cut. No Run keeps working. The journal itself
            # is never touched: rows are added, never deleted.
            # Test-first history: this failed here before Red button
            # existed. Charles approved the test, then it was built.
            self.assertTrue(
                hasattr(self.proxy.state, "red_button"),
                "Red button does not exist",
            )
            rows_before = sum(len(self.rows_for(t)) for t in (trace1, trace2, trace3))
            stopped = self.proxy.state.red_button(reason="human red button")
            self.assertTrue(stopped, "red_button refused to stop all Runs")
            rows_after = sum(len(self.rows_for(t)) for t in (trace1, trace2, trace3))
            self.assertGreater(rows_after, rows_before, "journal must grow, never shrink")

            # Step 5: Run 1, Run 2, and paused Run 3 each have a stop row:
            # outcome stopped, reason human red button, verdict Unverified
            # explicitly: status unknown, never Correct, never Incorrect,
            # and never "failed" in a human-visible summary.
            for trace in (trace1, trace2, trace3):
                stop_rows = [
                    r for r in self.rows_for(trace)
                    if r["outcome"] == "stopped"
                ]
                self.assertTrue(stop_rows, f"no stop row for {trace}")
                stop_row = stop_rows[-1]
                self.assertEqual(stop_row["trace_id"], trace)
                self.assertEqual(stop_row["reason"], "human red button")
                self.assertTrue(stop_row["created_at"], "stop needs a timestamp")
                # Unverified, explicitly: a stop alone verifies nothing,
                # so the verdict must read Unknown, never Correct and
                # never Incorrect. Unknown is the explicit state.
                self.assertEqual(
                    stop_row["status"], "unknown",
                    "stop verdict must be Unverified, explicitly")
                row_text = " ".join(
                    str(stop_row[k]) for k in stop_row.keys())
                self.assertNotIn("Authorization", row_text)
                self.assertNotIn("Bearer", row_text)
            # Every live tunnel is cut: no further bytes flow, for any Run.
            for sock in (sock1, sock2):
                with self.assertRaises((OSError, socket.timeout)):
                    sock.settimeout(2)
                    sock.sendall(b"run-after-red-button")
                    self.assertEqual(
                        self.echo_roundtrip(sock, b"run-after-red-button"), b"")

            # Step 6: a new Run started after Red button, without a fresh
            # human approval and Verify, is refused and journaled. The
            # proxy must not fail open to a new Run.
            d_before = self.echoes[3].count
            sock4, status4 = self.connect_status(self.destD, trace4)
            sock4.close()
            self.assertEqual(status4, 503, "new Run without approval must be refused")
            self.assertEqual(self.echoes[3].count, d_before, "nothing reached D")
            refused_rows = [
                r for r in self.rows_for(trace4)
                if r["reason"] == "approval required after red button"
            ]
            self.assertTrue(refused_rows, "refused new Run must be journaled")
            self.assertEqual(refused_rows[-1]["status"], "unknown")
            self.assertEqual(refused_rows[-1]["outcome"], "stopped")

            # Step 7: after a fresh Verify and a fresh human approval, a
            # new Run is allowed and journaled. Old Runs stay stopped and
            # never restart on their own.
            self.assertFalse(
                self.proxy.state.approve_run(trace1, done_clause=done),
                "old Runs stay stopped: approval is for new Runs only",
            )
            allowed, _ = self.proxy.state.retry_run(trace1)
            self.assertFalse(allowed, "old Runs stay stopped: no retry")
            self.assertTrue(
                [r for r in self.rows_for(trace1)
                 if r["reason"] == "red button stopped"],
                "blocked retry on an old Run must be journaled",
            )
            self.assertTrue(
                self.proxy.state.approve_run(trace4, done_clause=done),
                "fresh human approval must be accepted for a new Run",
            )
            self.assertTrue(
                [r for r in self.rows_for(trace4)
                 if r["reason"] == "fresh approval recorded"],
                "fresh approval must be journaled",
            )
            proof_path = os.path.join(self.tmp.name, "red-button-done-proof.txt")
            with open(proof_path, "w") as proof:
                proof.write("row exists after close/fsync")
                proof.flush()
                os.fsync(proof.fileno())
            with open(proof_path) as proof:
                self.assertEqual(proof.read(), "row exists after close/fsync")
            self.assertTrue(
                self.proxy.state.verify_run(trace4, done_clause=done),
                "fresh Verify must pass for an approved new Run",
            )
            d_before = self.echoes[3].count
            sock4_new = self.open_tunnel(self.destD, trace4)
            try:
                self.assertEqual(
                    self.echo_roundtrip(sock4_new, b"run4-on-D"), b"run4-on-D")
                self.assertEqual(self.echoes[3].count, d_before + 1)
            finally:
                sock4_new.close()
            landed = self.wait_row(
                trace4, lambda r: r["dest_host"] == self.destD and r["outcome"] == "allowed",
                "allowed tunnel row on D",
            )
            self.assertEqual(landed["status"], "success")
        finally:
            sock1.close()
            sock2.close()


if __name__ == "__main__":
    unittest.main()
