"""Concurrent log_attempt calls on one shared connection must not fail."""
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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


if __name__ == "__main__":
    unittest.main()
