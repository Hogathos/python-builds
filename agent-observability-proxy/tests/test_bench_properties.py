"""Bench property tests, Part A: invariants that must hold, always.

Five properties, each runnable alone (`pytest tests/test_bench_properties.py -k <name>`).
No scores, no judges: each property states one rule and checks it over
generated inputs. Hypothesis is a test dependency only.
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

from hypothesis import given, settings
from hypothesis import strategies as st

import api as api_module
import db as db_module
import proxy as proxy_module


def _no_db_cache(fn):
    """Hypothesis without an on-disk example cache: clean worktree."""
    return settings(max_examples=50, deadline=None, database=None)(fn)


class _EchoHandler(socketserver.BaseRequestHandler):
    def handle(self):
        while True:
            data = self.request.recv(65536)
            if not data:
                return
            self.request.sendall(data)


class AccountingPropertyTest(unittest.TestCase):
    """Outcome accounting always reconciles, for any mix of outcomes."""

    @_no_db_cache
    @given(st.lists(
        st.sampled_from(["allowed", "blocked", "rate_limited", "paused",
                         "redirected", "stopped", "verified", "",
                         "legacy-outcome", "OTHER"]),
        min_size=0, max_size=25))
    def test_outcome_counts_always_reconcile(self, outcomes):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        conn = db_module.init_db(os.path.join(tmp.name, "bench.db"))
        self.addCleanup(conn.close)
        for i, outcome in enumerate(outcomes):
            db_module.log_attempt(
                conn, trace_id=f"bench-t-{i % 5}", task_number=1,
                attempt=1, status="success", dest_host="127.0.0.1",
                endpoint="/x", method="GET", outcome=outcome)
        counts = db_module.fetch_outcome_counts(conn)
        total = conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
        self.assertEqual(total, len(outcomes))
        self.assertEqual(
            counts["allowed"] + counts["blocked"]
            + counts["rate_limited"] + counts["paused"]
            + counts["redirected"] + counts["stopped"]
            + counts["verified"] + counts["other"],
            total)


class CostPropertyTest(unittest.TestCase):
    """Priced cost rules hold for any row: free outcomes $0.00, recorded
    nonzero cost wins, loopback $0.00, else Unverified (None), never
    guessed."""

    @_no_db_cache
    @given(
        outcome=st.sampled_from(["allowed", "blocked", "rate_limited",
                                 "paused", "redirected", "stopped",
                                 "verified", "", "legacy"]),
        dest=st.sampled_from(["127.0.0.1", "127.0.0.1:8888", "localhost",
                              "::1", "[::1]:9000", "pay.example.com",
                              "exfil.example.test"]),
        cost=st.floats(allow_nan=False, allow_infinity=False,
                       min_value=0.0, max_value=10.0))
    def test_priced_cost_rules(self, outcome, dest, cost):
        row = {"outcome": outcome, "status": "success",
               "dest_host": dest, "cost_dollars": cost}
        got = api_module.attempt_cost(row)
        if outcome in ("blocked", "rate_limited", "paused",
                       "redirected", "stopped", "verified"):
            self.assertEqual(got, 0.0)
        elif cost:
            self.assertEqual(got, cost)
        elif dest in ("127.0.0.1", "localhost", "::1"):
            self.assertEqual(got, 0.0)
        else:
            host, _, port = dest.rpartition(":")
            if port.isdigit() and host in ("127.0.0.1", "localhost", "::1"):
                self.assertEqual(got, 0.0)
            else:
                self.assertIsNone(got)


class LiveProxyPropertyBase(unittest.TestCase):
    """One shared proxy + echo upstream for the live-tunnel properties."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.tmp.name, "attempts.db")
        cls.echo = socketserver.ThreadingTCPServer(
            ("127.0.0.1", 0), _EchoHandler)
        cls.echo_port = cls.echo.server_address[1]
        threading.Thread(target=cls.echo.serve_forever, daemon=True).start()
        # High rate limit: rate limiting has its own tests; these
        # properties must never trip it, or a 429 would mask the 503
        # cut refusal the assertions check for.
        cls.proxy = proxy_module.serve(
            "127.0.0.1", 0, cls.db_path, rate_limit=10000)
        cls.proxy_port = cls.proxy.server_address[1]
        threading.Thread(target=cls.proxy.serve_forever, daemon=True).start()
        cls.dest = f"127.0.0.1:{cls.echo_port}"
        cls._n = 0

    @classmethod
    def tearDownClass(cls):
        cls.proxy.shutdown()
        cls.echo.shutdown()
        cls.proxy.server_close()
        cls.echo.server_close()
        cls.proxy.state.conn.close()
        cls.tmp.cleanup()

    def rows_for(self, trace_id):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(
                "SELECT * FROM attempts WHERE trace_id = ? ORDER BY id",
                (trace_id,)).fetchall()
        finally:
            conn.close()

    def open_tunnel(self, dest, trace_id):
        sock = socket.create_connection(
            ("127.0.0.1", self.proxy_port), timeout=5)
        sock.settimeout(5)
        sock.sendall(
            (f"CONNECT {dest} HTTP/1.1\r\nHost: {dest}\r\n"
             f"X-Trace-Id: {trace_id}\r\n\r\n").encode())
        raw = b""
        while b"\r\n\r\n" not in raw:
            chunk = sock.recv(65536)
            self.assertTrue(chunk)
            raw += chunk
        head = raw.split(b"\r\n\r\n", 1)[0].decode(errors="replace")
        return sock, int(head.split()[1])

    def fresh_trace(self, prefix):
        type(self)._n += 1
        return f"bench-{prefix}-{type(self)._n}"

    def assert_tunnel_dead(self, sock):
        """A cut tunnel carries no more bytes: EOF or error, never echo."""
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


class PauseDestPropertyTest(LiveProxyPropertyBase):
    """Pause rows name the live destination, never '', for any trace."""

    @settings(max_examples=30, deadline=None, database=None)
    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
                   min_size=1, max_size=12))
    def test_pause_row_names_live_destination(self, slug):
        trace = self.fresh_trace(f"dest-{slug}")
        sock = self.open_tunnel(self.dest, trace)[0]
        try:
            self.assertTrue(self.proxy.state.pause_run(trace))
            rows = [r for r in self.rows_for(trace)
                    if r["outcome"] == "paused"]
            self.assertTrue(rows, "pause must be journaled")
            self.assertEqual(rows[-1]["dest_host"], self.dest)
        finally:
            sock.close()


class JournalBeforeCutPropertyTest(LiveProxyPropertyBase):
    """Journal first, then cut: the pause row exists the moment pause
    returns, and no new tunnel opens after, for any set of runs."""

    @settings(max_examples=20, deadline=None, database=None)
    @given(st.lists(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
                min_size=1, max_size=8),
        min_size=1, max_size=8, unique=True))
    def test_pause_journals_before_cutting(self, slugs):
        traces = [self.fresh_trace(f"cut-{s}") for s in slugs]
        socks = [self.open_tunnel(self.dest, t)[0] for t in traces]
        try:
            for trace in traces:
                self.assertTrue(
                    self.proxy.state.pause_run(trace, reason="human pause"))
            for trace in traces:
                rows = [r for r in self.rows_for(trace)
                        if r["outcome"] == "paused"]
                self.assertTrue(rows, f"no pause row for {trace}")
                self.assertEqual(rows[0]["dest_host"], self.dest)
            for trace in traces:
                sock, status = self.open_tunnel(self.dest, trace)
                sock.close()
                self.assertEqual(status, 503, f"{trace} must stay cut")
        finally:
            for sock in socks:
                sock.close()


class TunnelDeadPropertyTest(LiveProxyPropertyBase):
    """A cut tunnel never echoes again, for any payload bytes."""

    @settings(max_examples=30, deadline=None, database=None)
    @given(st.binary(min_size=1, max_size=256))
    def test_cut_tunnel_carries_no_more_bytes(self, payload):
        trace = self.fresh_trace("dead")
        sock = self.open_tunnel(self.dest, trace)[0]
        try:
            self.assertTrue(self.proxy.state.pause_run(trace))
            sock.settimeout(5)
            try:
                sock.sendall(payload)
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
            self.assertNotEqual(data, payload, "cut tunnel echoed")
        finally:
            sock.close()


if __name__ == "__main__":
    unittest.main()
