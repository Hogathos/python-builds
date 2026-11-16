"""Steer Pause-one-Run test (test-first, failing until Pause is built).

One test only: test_pause_one_run_cuts_tunnel_only_that_run.

Problem in one sentence: Iris can observe an agent, but cannot pause it
yet, so a bad Run keeps going after Iris should have stopped it.

Done clause for this test Run (human-approved, once per task type,
as a named read-back, before the Run starts):
  task_type = "local file write"
  clause    = "row exists after close/fsync"
  read_back = "named read-back: file row exists after close/fsync"
No approved done = Unverified, never Correct.

Expected failure right now: the Pause endpoint does not exist, or does not cut the tunnel, and that failure was the correct
test-first proof. Charles approved the test in Main, then Pause was
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
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# urllib honors NO_PROXY and would bypass the loopback test proxy;
# drop it so the suite never depends on ambient proxy config.
os.environ.pop("NO_PROXY", None)
os.environ.pop("no_proxy", None)

import proxy as proxy_module
import server as server_module


# Human-approved "done" clause for this test Run, once per task type,
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


class SteerPauseOneRunTest(unittest.TestCase):
    """Pause one Run by cutting the tunnel for that Run only."""

    @classmethod
    def setUpClass(cls):
        """Start two loopback echo destinations and one proxy on temp db."""
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.tmp.name, "attempts.db")
        cls.echo1 = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _EchoHandler)
        cls.echo1_port = cls.echo1.server_address[1]
        threading.Thread(target=cls.echo1.serve_forever, daemon=True).start()
        cls.echo2 = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _EchoHandler)
        cls.echo2_port = cls.echo2.server_address[1]
        threading.Thread(target=cls.echo2.serve_forever, daemon=True).start()
        cls.proxy = proxy_module.serve("127.0.0.1", 0, cls.db_path)
        cls.proxy_port = cls.proxy.server_address[1]
        threading.Thread(target=cls.proxy.serve_forever, daemon=True).start()
        cls.dest1 = f"127.0.0.1:{cls.echo1_port}"
        cls.dest2 = f"127.0.0.1:{cls.echo2_port}"
        # One plain-HTTP upstream, so Pause is proven for HTTP too,
        # not only for CONNECT tunnels. Loopback only.
        cls.http_upstream = ThreadingHTTPServer(
            ("127.0.0.1", 0), server_module.Handler)
        cls.http_port = cls.http_upstream.server_address[1]
        threading.Thread(
            target=cls.http_upstream.serve_forever, daemon=True).start()
        cls.http_base = f"http://127.0.0.1:{cls.http_port}"
        cls.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler(
                {"http": f"http://127.0.0.1:{cls.proxy_port}"}))

    @classmethod
    def tearDownClass(cls):
        """Shut down proxy, echoes, HTTP upstream, temp db. No files left."""
        cls.proxy.shutdown()
        cls.echo1.shutdown()
        cls.echo2.shutdown()
        cls.http_upstream.shutdown()
        cls.proxy.server_close()
        cls.echo1.server_close()
        cls.echo2.server_close()
        cls.http_upstream.server_close()
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

    def http_get(self, path, trace):
        """One plain-HTTP GET through the proxy. Returns status code."""
        req = urllib.request.Request(self.http_base + path)
        req.add_header("X-Trace-Id", trace)
        try:
            with self.opener.open(req, timeout=10) as resp:
                resp.read()
                return resp.status
        except urllib.error.HTTPError as exc:
            exc.read()
            return exc.code

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

    def test_pause_one_run_cuts_tunnel_only_that_run(self):
        """Pause Run 1 cuts its tunnel; Run 2 keeps flowing; retry needs Verify."""
        # Step 1: test Run 1 starts WITH a human-approved done clause.
        # Without this clause the Run verdict could never be Correct.
        done = HUMAN_APPROVED_DONE
        self.assertEqual(done["approved_by"], "human")
        self.assertIn("read-back", done["read_back"])
        trace1 = "steer-pause-test-run-1"
        trace2 = "steer-pause-test-run-2"
        self.assertNotEqual(trace1, trace2)

        # Step 2: second test Run, different trace_id, different
        # destination, loopback only. Both destinations are 127.0.0.1.
        sock1 = self.open_tunnel(self.dest1, trace1)
        sock2 = self.open_tunnel(self.dest2, trace2)
        try:
            self.assertEqual(self.echo_roundtrip(sock1, b"run1-before"), b"run1-before")
            self.assertEqual(self.echo_roundtrip(sock2, b"run2-before"), b"run2-before")

            # Step 3: Pause Run 1 only. Human-only endpoint, NOT
            # agent-callable (a plain state method, no HTTP route, so
            # proxied traffic cannot call it), local-first, fail-closed:
            # if Iris dies, the agent stops, not continues. Journal
            # BEFORE the pause takes effect: journal row first, then cut.
            self.assertTrue(
                hasattr(self.proxy.state, "pause_run"),
                "Pause endpoint does not exist",
            )
            paused = self.proxy.state.pause_run(trace1, reason="human pause")
            self.assertTrue(paused, "pause_run refused Run 1")

            # Step 4: Run 1 tunnel is cut, no further bytes flow for Run 1.
            # Journal row exists: timestamp, trace_id, destination,
            # method, outcome = paused, reason = human pause / Steer
            # pause, verdict = Unverified (never Correct, never
            # Incorrect from a pause alone). Metadata only.
            with self.assertRaises((OSError, socket.timeout)):
                sock1.settimeout(2)
                sock1.sendall(b"run1-after-pause")
                self.assertEqual(self.echo_roundtrip(sock1, b"run1-after-pause"), b"")
            pause_rows = [
                r for r in self.rows_for(trace1)
                if r["outcome"] == "paused"
            ]
            self.assertTrue(pause_rows, "no journal row with outcome=paused for Run 1")
            pause_row = pause_rows[-1]
            self.assertEqual(pause_row["trace_id"], trace1)
            self.assertIn(self.dest1, pause_row["dest_host"])
            self.assertIn(pause_row["reason"], ("human pause", "Steer pause"))
            self.assertTrue(pause_row["created_at"], "pause row needs a timestamp")
            # Unverified, explicitly: a pause alone verifies nothing,
            # so the verdict must read Unknown, never Correct and never
            # Incorrect. Unknown is the explicit state, not a guess.
            self.assertEqual(
                pause_row["status"], "unknown",
                "pause verdict must be Unverified, explicitly")
            # No bodies, no keys, no secrets in the row.
            row_text = " ".join(str(pause_row[k]) for k in pause_row.keys())
            self.assertNotIn("Authorization", row_text)
            self.assertNotIn("Bearer", row_text)

            # Step 5: Run 2 tunnel is NOT cut. Bytes still flow for Run 2,
            # and no pause row exists for Run 2.
            self.assertEqual(self.echo_roundtrip(sock2, b"run2-after"), b"run2-after")
            self.assertEqual(
                [r for r in self.rows_for(trace2) if r["outcome"] == "paused"],
                [],
                "Run 2 must have no pause row",
            )
            # Plain HTTP follows the same rule, by trace_id, not by
            # destination: Run 2 still flows, Run 1 is refused without
            # forwarding anything.
            self.assertEqual(self.http_get("/echo", trace2), 200)
            self.assertEqual(self.http_get("/echo", trace1), 503)

            # Step 6: retry for Run 1 without a fresh Verify is blocked,
            # and the block is journaled with reason = verify required.
            self.assertTrue(
                hasattr(self.proxy.state, "retry_run"),
                "retry_run does not exist",
            )
            allowed, why = self.proxy.state.retry_run(trace1)
            self.assertFalse(allowed, "retry without Verify must be blocked")
            self.assertIn("verify", why.lower())
            blocked_rows = [
                r for r in self.rows_for(trace1)
                if "verify required before retry" in r["reason"]
            ]
            self.assertTrue(blocked_rows, "blocked retry must be journaled")

            # Step 7: after a fresh Verify, with a read that could have
            # failed (the named read-back), retry is allowed, and
            # journaled. The read-back is executed here: written,
            # synced, read back. That read could have failed (missing
            # file, short read); only then does the Verify count.
            proof_path = os.path.join(self.tmp.name, "done-proof.txt")
            with open(proof_path, "w") as proof:
                proof.write("row exists after close/fsync")
                proof.flush()
                os.fsync(proof.fileno())
            with open(proof_path) as proof:
                self.assertEqual(proof.read(), "row exists after close/fsync")
            self.assertTrue(
                hasattr(self.proxy.state, "verify_run"),
                "verify_run does not exist",
            )
            verified = self.proxy.state.verify_run(trace1, done_clause=done)
            self.assertTrue(verified, "fresh Verify with a failing-capable read must pass")
            self.assertTrue(
                [r for r in self.rows_for(trace1)
                 if r["reason"] == "verify ok"],
                "fresh Verify must be journaled",
            )
            allowed, _ = self.proxy.state.retry_run(trace1)
            self.assertTrue(allowed, "retry after fresh Verify must be allowed")
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
