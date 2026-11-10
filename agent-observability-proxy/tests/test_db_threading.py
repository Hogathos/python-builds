"""Concurrent log_attempt calls on one shared connection must not fail."""
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# urllib honors NO_PROXY and would bypass the loopback test proxy;
# drop it so the suite never depends on ambient proxy config (N7).
os.environ.pop("NO_PROXY", None); os.environ.pop("no_proxy", None)

import db


class ConcurrentLogAttemptTest(unittest.TestCase):
    def test_many_threads_share_one_connection(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = db.init_db(os.path.join(tmp, "attempts.db"))
            errors = []

            def worker(worker_id):
                try:
                    for i in range(25):
                        db.log_attempt(
                            conn,
                            trace_id=f"trace-{worker_id}-{i}",
                            task_number=worker_id,
                            attempt=1,
                            status="success",
                        )
                except Exception as exc:  # collected and asserted below
                    errors.append(exc)

            threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            count = conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
            conn.close()
            self.assertEqual(errors, [])
            self.assertEqual(count, 8 * 25)


    def test_concurrent_stamps_stay_inside_lock_and_ordered_with_id(self):
        import datetime as datetime_module
        import types
        real_datetime_module = db.datetime
        real_lock = db._write_lock
        real_datetime = datetime_module.datetime
        events = []
        guard = threading.Lock()
        seq = [0]

        def record(kind):
            with guard:
                seq[0] += 1
                events.append((threading.get_ident(), kind))

        class RecordingLock:
            def __enter__(self):
                real_lock.acquire()
                record("acquired")
                return self

            def __exit__(self, *exc):
                record("released")
                real_lock.release()
                return False

        class RecordingDateTime(real_datetime):
            @classmethod
            def now(cls, tz=None):
                record("now")
                return real_datetime.now(tz)

        db.datetime = types.SimpleNamespace(
            datetime=RecordingDateTime, timezone=datetime_module.timezone)
        db._write_lock = RecordingLock()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                conn = db.init_db(os.path.join(tmp, "attempts.db"))
                try:
                    errors = []
                    barrier = threading.Barrier(2)

                    def worker(worker_id):
                        try:
                            barrier.wait()
                            for i in range(10):
                                db.log_attempt(
                                    conn, trace_id="trace-race",
                                    task_number=worker_id, attempt=1,
                                    status="success")
                        except Exception as exc:
                            errors.append(exc)

                    threads = [threading.Thread(target=worker, args=(n,))
                               for n in (1, 2)]
                    for thread in threads:
                        thread.start()
                    for thread in threads:
                        thread.join()
                    self.assertEqual(errors, [])

                    by_thread = {}
                    for ident, kind in events:
                        by_thread.setdefault(ident, []).append(kind)
                    for kinds in by_thread.values():
                        holding = False
                        for kind in kinds:
                            if kind == "acquired":
                                holding = True
                            elif kind == "released":
                                holding = False
                            elif kind == "now":
                                self.assertTrue(
                                    holding,
                                    "created_at stamped outside _write_lock")

                    rows = conn.execute(
                        "SELECT id, created_at FROM attempts ORDER BY id"
                    ).fetchall()
                finally:
                    conn.close()
            stamps = [row[1] for row in rows]
            self.assertEqual(stamps, sorted(stamps))
        finally:
            db.datetime = real_datetime_module
            db._write_lock = real_lock


if __name__ == "__main__":
    unittest.main()
