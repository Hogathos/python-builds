"""Verify first test (test-first: failed until Verify read-back was built).

One test only: test_verify_read_back_local_file_sqlite.

Problem in one sentence: Verify must check what the agent said it did,
against what actually happened, by reading it back, and say Correct,
Incorrect, or Unverified, with a journal before the call, no scores,
no LLM-as-judge.

Done clauses for this test (human-approved, once per task type,
as named read-backs, before the Run starts):
  task_type = "local file write"
  clause    = "row exists after close/fsync"
  read_back = "named read-back: file row exists after close/fsync"
  task_type = "local SQLite insert"
  clause    = "row exists after COMMIT"
  read_back = "named read-back: SELECT in a new transaction after COMMIT"
No approved done = Unverified, never Correct.

Test-first history: this test FAILED at Step 2 before Verify
read-back existed, and that failure was the correct proof. Charles
approved the test in Main, then Verify was implemented. The test now
proves the behavior.

Plain words, for evaluators: Verify means check what the agent said it
did, against what actually happened, by reading it back, and say
Correct, Incorrect, or Unverified.

Loopback only. Metadata only in journal rows. No bodies, no keys,
no Authorization headers, no real hostnames. No scores, no percentages,
no "probably correct".
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


# Human-approved "done" clauses for this test, once per task type,
# as named read-backs, fixed before the Run starts.
DONE_FILE = {
    "task_type": "local file write",
    "clause": "row exists after close/fsync",
    "read_back": "named read-back: file row exists after close/fsync",
    "approved_by": "human",
}
DONE_SQLITE = {
    "task_type": "local SQLite insert",
    "clause": "row exists after COMMIT",
    "read_back": "named read-back: SELECT in a new transaction after COMMIT",
    "approved_by": "human",
}


class _CountingEchoHandler(socketserver.BaseRequestHandler):
    """Loopback echo upstream that counts its own connections."""

    def handle(self):
        self.server.count += 1
        while True:
            data = self.request.recv(65536)
            if not data:
                return
            self.request.sendall(data)


class VerifyReadBackLocalTest(unittest.TestCase):
    """Verify by independent local read-back: Correct, Incorrect, Unverified."""

    @classmethod
    def setUpClass(cls):
        """Start one loopback echo destination and one proxy on temp db."""
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.tmp.name, "attempts.db")
        cls.echo = socketserver.ThreadingTCPServer(
            ("127.0.0.1", 0), _CountingEchoHandler)
        cls.echo.count = 0
        threading.Thread(target=cls.echo.serve_forever, daemon=True).start()
        cls.proxy = proxy_module.serve("127.0.0.1", 0, cls.db_path)
        cls.proxy_port = cls.proxy.server_address[1]
        threading.Thread(target=cls.proxy.serve_forever, daemon=True).start()
        cls.destA = f"127.0.0.1:{cls.echo.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        """Shut down proxy, echo, and temp db. No files left behind."""
        cls.proxy.shutdown()
        cls.echo.shutdown()
        cls.proxy.server_close()
        cls.echo.server_close()
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

    def check_card(self, card, verdict):
        """Plain-words card shape: claim, read, source, time, verdict, why, next."""
        for key in ("claim", "what_read", "source", "as_of",
                    "verdict", "why", "next"):
            self.assertIn(key, card, f"card missing {key}")
            self.assertTrue(card[key], f"card {key} must not be empty")
        self.assertEqual(card["verdict"], verdict)
        self.assertNotIn("\n", card["why"], "why is one line")
        self.assertNotIn("probably", card["why"].lower())
        self.assertNotIn("%", card["why"])

    def test_verify_read_back_local_file_sqlite(self):
        """Local file + SQLite read profiles: Correct, Incorrect, Unverified."""
        # Step 1: test Run starts WITH a human-approved done clause, for
        # a local file write on loopback. Without this clause the Run
        # verdict could never be Correct.
        self.assertEqual(DONE_FILE["approved_by"], "human")
        self.assertIn("read-back", DONE_FILE["read_back"])
        self.assertEqual(DONE_SQLITE["approved_by"], "human")
        trace_ok = "verify-local-run-ok"
        trace_bad = "verify-local-run-bad"
        trace_unknown = "verify-local-run-unknown"
        self.assertEqual(len({trace_ok, trace_bad, trace_unknown}), 3)

        # Agent effects, written the way a real agent would: file synced
        # to disk, SQLite row committed. Both reads below happen after.
        file_path = os.path.join(self.tmp.name, "agent-effect.txt")
        with open(file_path, "w") as proof:
            proof.write("Alice")
            proof.flush()
            os.fsync(proof.fileno())
        effect_db = os.path.join(self.tmp.name, "agent-effect.db")
        conn = sqlite3.connect(effect_db)
        conn.execute("CREATE TABLE users (name TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO users (name) VALUES (?)", ("Alice",))
        conn.commit()
        conn.close()

        # Step 2: Verify reads back, by independent read, after settle,
        # after close/fsync and COMMIT. Not from the agent's own claim,
        # not from the agent's own log, not from a score, not from an LLM.
        # Test-first history: this failed here before Verify
        # existed. Charles approved the test, then it was built.
        self.assertTrue(
            hasattr(self.proxy.state, "verify_read_back"),
            "Verify read-back does not exist",
        )
        file_claim = {
            "kind": "local-file",
            "path": file_path,
            "expected_text": "Alice",
            "idempotency_key": "verify-ok-file-1",
        }
        verdict, card = self.proxy.state.verify_read_back(
            trace_ok, file_claim, done_clause=DONE_FILE)
        self.assertEqual(verdict, "Correct")
        self.check_card(card, "Correct")
        db_claim = {
            "kind": "sqlite",
            "db": effect_db,
            "sql": "SELECT name FROM users WHERE name = ?",
            "params": ["Alice"],
            "expected_rows": [["Alice"]],
            "idempotency_key": "verify-ok-sqlite-1",
        }
        verdict, card = self.proxy.state.verify_read_back(
            trace_ok, db_claim, done_clause=DONE_SQLITE)
        self.assertEqual(verdict, "Correct")
        self.check_card(card, "Correct")

        # Step 3: read matches claim, every part checked against the real
        # effect, all passed: verdict Correct, journaled, with a
        # plain-words card (claim, what was read, from where, as of when,
        # verdict Correct, one-line why, next step).
        call_rows = [
            r for r in self.rows_for(trace_ok)
            if r["outcome"] == "verified"
        ]
        self.assertTrue(call_rows, "Verify call must be journaled")
        verdict_rows = [r for r in call_rows if r["status"] == "success"]
        self.assertTrue(verdict_rows, "Correct verdict must be journaled")
        for row in verdict_rows:
            self.assertTrue(row["created_at"], "verdict needs a timestamp")
            row_text = " ".join(str(row[k]) for k in row.keys())
            self.assertNotIn("Authorization", row_text)
            self.assertNotIn("Bearer", row_text)
            self.assertNotIn("Alice", row_text, "no bodies in the journal")

        # Step 4: read contradicts claim, miss in a fresh transaction, row
        # does not exist: verdict Incorrect, the agent is stopped, and it
        # is journaled with a plain-words card.
        missing_claim = {
            "kind": "sqlite",
            "db": effect_db,
            "sql": "SELECT name FROM users WHERE name = ?",
            "params": ["Nobody"],
            "expected_rows": [["Nobody"]],
            "idempotency_key": "verify-bad-sqlite-1",
        }
        verdict, card = self.proxy.state.verify_read_back(
            trace_bad, missing_claim, done_clause=DONE_SQLITE)
        self.assertEqual(verdict, "Incorrect")
        self.check_card(card, "Incorrect")
        bad_verdict = [
            r for r in self.rows_for(trace_bad)
            if r["outcome"] == "verified" and r["status"] == "failure"
        ]
        self.assertTrue(bad_verdict, "Incorrect verdict must be journaled")
        # Thus the agent was stopped: no new tunnel for that Run.
        self.assertTrue(self.proxy.state.is_paused(trace_bad),
                        "Incorrect verdict must stop the Run")
        sock, status = self.open_tunnel(self.destA, trace_bad)
        sock.close()
        self.assertEqual(status, 503, "stopped Run moves no bytes")
        self.assertEqual(self.echo.count, 0, "nothing reached upstream")

        # Step 5: read cannot be done: no approved done clause, no read
        # profile, remote effect with no local proof. Verdict Unverified,
        # journaled, plain-words card. No score, no percentage, no
        # "probably correct". Remote stays Unverified unless something
        # local proves it; V1 has public read plus human confirm only.
        no_done_claim = dict(file_claim, idempotency_key="verify-unknown-1")
        verdict, card = self.proxy.state.verify_read_back(
            trace_unknown, no_done_claim, done_clause=None)
        self.assertEqual(verdict, "Unverified")
        self.check_card(card, "Unverified")
        remote_claim = {
            "kind": "remote",
            "system": "stripe",
            "reference": "pi_test_123",
            "idempotency_key": "verify-unknown-2",
        }
        verdict, card = self.proxy.state.verify_read_back(
            trace_unknown, remote_claim, done_clause=DONE_FILE)
        self.assertEqual(verdict, "Unverified", "remote with no local proof stays Unverified")
        self.check_card(card, "Unverified")
        unknown_rows = [
            r for r in self.rows_for(trace_unknown)
            if r["outcome"] == "verified" and r["status"] == "unknown"
        ]
        self.assertTrue(unknown_rows, "Unverified verdict must be journaled")

        # Step 6: journal before call. The call row is committed before
        # Verify reads, before Verify calls, before Verify stops. Verdict
        # and Retry-allowed are separate: a Correct verdict alone does
        # not allow a retry; without a fresh Verify the retry is blocked
        # and journaled.
        keyed = [r for r in self.rows_for(trace_ok)
                 if "verify-ok-file-1" in (r["reason"] or "")]
        self.assertTrue(keyed, "call row must carry the idempotency key")
        call_row = keyed[0]
        later_verdict = [r for r in self.rows_for(trace_ok)
                         if r["outcome"] == "verified"
                         and r["status"] == "success"]
        self.assertTrue(later_verdict, "verdict row must exist")
        self.assertLess(call_row["id"], later_verdict[0]["id"],
                        "call row first, verdict after")
        allowed, _ = self.proxy.state.retry_run(trace_bad)
        self.assertFalse(allowed, "retry without Verify must be blocked")
        self.assertTrue(
            [r for r in self.rows_for(trace_bad)
             if r["reason"] == "verify required before retry"],
            "blocked retry must be journaled",
        )

        # Step 7: retry after a fresh Verify, with a fresh human
        # approval in the done clause, is allowed and journaled. The old
        # Run stays paused until Verify: it never restarts on its own.
        self.assertTrue(
            self.proxy.state.verify_run(trace_bad, done_clause=DONE_SQLITE),
            "fresh Verify must pass",
        )
        allowed, _ = self.proxy.state.retry_run(trace_bad)
        self.assertTrue(allowed, "retry after fresh Verify must be allowed")
        self.assertTrue(
            [r for r in self.rows_for(trace_bad)
             if r["reason"] == "retry allowed after verify"],
            "allowed retry must be journaled",
        )


if __name__ == "__main__":
    unittest.main()
