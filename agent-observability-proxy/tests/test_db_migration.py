"""Two processes opening the same pre-M4 database must both open cleanly."""
import multiprocessing
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# urllib honors NO_PROXY and would bypass the loopback test proxy;
# drop it so the suite never depends on ambient proxy config (N7).
os.environ.pop("NO_PROXY", None); os.environ.pop("no_proxy", None)

import db


def _open_db(path, barrier, queue):
    try:
        barrier.wait(timeout=30)
        conn = db.init_db(path)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(attempts)")}
        conn.close()
        queue.put(("ok", "outcome" in cols and "reason" in cols))
    except Exception as exc:  # reported back, never raised in the child
        queue.put(("error", repr(exc)))


def _make_pre_m4_db(path):
    conn = db.init_db(path)
    conn.execute("ALTER TABLE attempts DROP COLUMN outcome")
    conn.execute("ALTER TABLE attempts DROP COLUMN reason")
    conn.commit()
    cols = {row[1] for row in conn.execute("PRAGMA table_info(attempts)")}
    conn.close()
    assert "outcome" not in cols and "reason" not in cols
    return path


class ConcurrentMigrationTest(unittest.TestCase):
    def test_two_processes_migrate_pre_m4_db_cleanly(self):
        ctx = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory() as tmp:
            for round_no in range(5):
                path = _make_pre_m4_db(
                    os.path.join(tmp, f"pre-m4-{round_no}.db"))
                barrier = ctx.Barrier(2)
                queue = ctx.Queue()
                procs = [ctx.Process(target=_open_db,
                                     args=(path, barrier, queue))
                         for _ in range(2)]
                for proc in procs:
                    proc.start()
                for proc in procs:
                    proc.join(timeout=60)
                    self.assertEqual(proc.exitcode, 0)
                results = [queue.get(timeout=10) for _ in procs]
                for status, detail in results:
                    self.assertEqual(status, "ok", detail)
                    self.assertTrue(detail)


if __name__ == "__main__":
    unittest.main()
