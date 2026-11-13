"""The default database must not depend on the working directory.

Double-clicking the standalone exe from inside dist/ used to silently
create dist/attempts.db, hiding traffic from the dashboard.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.pop("NO_PROXY", None); os.environ.pop("no_proxy", None)

import proxy

PROXY_DIR = os.path.dirname(os.path.abspath(proxy.__file__))


class DbDefaultPathTest(unittest.TestCase):
    def test_default_db_is_absolute_beside_proxy(self):
        args = proxy.build_parser().parse_args([])
        self.assertTrue(os.path.isabs(args.db), args.db)
        self.assertEqual(args.db, os.path.join(PROXY_DIR, "attempts.db"))

    def test_default_db_ignores_working_directory(self):
        here = os.path.abspath(os.getcwd())
        tmp = os.path.join(here, "tmpabmgjizx")
        os.chdir(tmp)
        try:
            args = proxy.build_parser().parse_args([])
        finally:
            os.chdir(here)
        self.assertEqual(args.db, os.path.join(PROXY_DIR, "attempts.db"))

    def test_frozen_exe_in_dist_uses_project_db(self):
        fake_exe = os.path.join("C:" + os.sep, "proj", "dist", "app.exe")
        with mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sys, "executable", fake_exe):
            self.assertEqual(proxy._default_db_path(),
                             os.path.join("C:" + os.sep, "proj", "attempts.db"))

    def test_frozen_exe_elsewhere_uses_exe_dir(self):
        fake_exe = os.path.join("C:" + os.sep, "tools", "app.exe")
        with mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sys, "executable", fake_exe):
            self.assertEqual(proxy._default_db_path(),
                             os.path.join("C:" + os.sep, "tools", "attempts.db"))

    def test_iris_passes_absolute_db(self):
        import iris
        db_flag = iris.PROXY_ARGS[iris.PROXY_ARGS.index("--db") + 1]
        self.assertTrue(os.path.isabs(db_flag), db_flag)
        self.assertTrue(db_flag.endswith("attempts.db"), db_flag)

    def test_launchers_pass_absolute_db(self):
        for bat in ("run-proxy.bat", "run-all.bat"):
            with open(os.path.join(PROXY_DIR, bat)) as f:
                body = f.read()
            self.assertIn('--db "%~dp0attempts.db"', body, bat)


if __name__ == "__main__":
    unittest.main()
