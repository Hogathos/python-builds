"""Devtool panel Pause button test (test-first, failing until built).

One test only: test_panel_pause_button_cuts_only_that_run.

Problem in one sentence: the devtool panel's Pause button must pause
one Run through the same human-only path as the proxy, cutting only
that Run, journal first, fail-closed.

The button will call devpanel.pause_run, a plain human-only function
in a dev-only module (separate file, clearly labeled dev only, never
shipped in the consumer app). No HTTP control route is added here:
the API stays GET-only, and the button wires to this function later.
The test drives the button's exact call, so the contract is pinned
before any panel code exists.

Done clause for this test Run (human-approved, once per task type,
as a named read-back, before the Run starts):
  task_type = "local file write"
  clause    = "row exists after close/fsync"
  read_back = "named read-back: file row exists after close/fsync"
No approved done = Unverified, never Correct.

Expected failure right now: the devpanel module does not exist, so
this test FAILS at import. That failure is correct. It is the
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
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# urllib honors NO_PROXY and would bypass the loopback test proxy;
# drop it so the suite never depends on ambient proxy config.
os.environ.pop("NO_PROXY", None)
os.environ.pop("no_proxy", None)

import devpanel as devpanel_module
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


class DevtoolPauseButtonTest(unittest.TestCase):
    """Panel Pause button pauses one Run; the other Run still flows."""

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
        self.proxy = proxy_module.serve("127.0.0.1", 0, self.db_path)
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

    def test_panel_pause_button_cuts_only_that_run(self):
        """Panel Pause button: Run A stops, Run B flows, retry needs Verify."""
        # Step 1: test Run starts WITH a human-approved done clause.
        done = HUMAN_APPROVED_DONE
        self.assertEqual(done["approved_by"], "human")
        self.assertIn("read-back", done["read_back"])
        traceA = "devtool-panel-run-A"
        traceB = "devtool-panel-run-B"
        self.assertNotEqual(traceA, traceB)

        # Step 2: two Runs on two loopback destinations, both flowing.
        sockA, statusA = self.open_tunnel(self.destA, traceA)
        sockB, statusB = self.open_tunnel(self.destB, traceB)
        self.assertEqual(statusA, 200)
        self.assertEqual(statusB, 200)
        try:
            self.assertEqual(self.echo_roundtrip(sockA, b"run-on-A"), b"run-on-A")
            self.assertEqual(self.echo_roundtrip(sockB, b"run-on-B"), b"run-on-B")

            # Step 3: the panel Pause button calls devpanel.pause_run,
            # a plain human-only function, never an HTTP route, so the
            # button cannot be tricked by proxied traffic into pausing.
            # Journal before the cut takes effect, fail-closed: if Iris
            # dies, the agent stops, not continues.
            # EXPECTED FAILURE (test-first): devpanel is missing.
            self.assertTrue(
                hasattr(devpanel_module, "pause_run"),
                "Pause button handler does not exist (expected failure, test-first)",
            )
            clicked = devpanel_module.pause_run(
                self.proxy.state, traceA, reason="human pause")
            self.assertTrue(clicked, "Pause button press refused Run A")

            # Step 4: only Run A stops. Its live tunnel is cut, new
            # tunnels for it are refused, Run B still flows, and the
            # journal row says outcome paused, status unknown:
            # Unverified, explicitly, never Correct, never Incorrect.
            self.assert_tunnel_dead(sockA)
            sockA2, statusA2 = self.open_tunnel(self.destA, traceA)
            sockA2.close()
            self.assertEqual(statusA2, 503, "paused Run stays cut")
            self.assertEqual(
                self.echo_roundtrip(sockB, b"run-still-on-B"),
                b"run-still-on-B",
            )
            pause_rows = [
                r for r in self.rows_for(traceA)
                if r["outcome"] == "paused"
            ]
            self.assertTrue(pause_rows, "button press must be journaled")
            pause_row = pause_rows[-1]
            self.assertEqual(pause_row["reason"], "human pause")
            self.assertEqual(
                pause_row["status"], "unknown",
                "pause verdict must be Unverified, explicitly")
            self.assertEqual(
                [r for r in self.rows_for(traceB) if r["outcome"] == "paused"],
                [],
                "other Run must have no pause row",
            )

            # Step 5: retry without a fresh Verify is blocked and
            # journaled. The button changes nothing about the Verify
            # gate: only verify_run stamps permission.
            allowed, why = self.proxy.state.retry_run(traceA)
            self.assertFalse(allowed, "retry without Verify must be blocked")
            self.assertIn("verify", why.lower())
            self.assertTrue(
                [r for r in self.rows_for(traceA)
                 if r["reason"] == "verify required before retry"],
                "blocked retry must be journaled",
            )
        finally:
            sockA.close()
            sockB.close()


if __name__ == "__main__":
    unittest.main()
