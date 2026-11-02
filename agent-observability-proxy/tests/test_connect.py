"""M2 tests: CONNECT tunnelling, metadata only, no payload/header logging."""
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

import proxy as proxy_module


class _EchoHandler(socketserver.BaseRequestHandler):
    def handle(self):
        while True:
            data = self.request.recv(65536)
            if not data:
                return
            self.request.sendall(data)


class M2ConnectTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.tmp.name, "attempts.db")
        cls.echo = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _EchoHandler)
        cls.echo_port = cls.echo.server_address[1]
        threading.Thread(target=cls.echo.serve_forever, daemon=True).start()
        cls.proxy = proxy_module.serve("127.0.0.1", 0, cls.db_path)
        cls.proxy_port = cls.proxy.server_address[1]
        threading.Thread(target=cls.proxy.serve_forever, daemon=True).start()
        cls.dest = f"127.0.0.1:{cls.echo_port}"

    @classmethod
    def tearDownClass(cls):
        cls.proxy.shutdown(); cls.echo.shutdown()
        cls.proxy.server_close(); cls.echo.server_close()
        cls.proxy.state.conn.close()
        cls.tmp.cleanup()

    def rows(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        out = conn.execute("SELECT * FROM attempts ORDER BY id").fetchall()
        conn.close()
        return out

    def wait_row(self, trace_id):
        for _ in range(50):
            mine = [r for r in self.rows() if r["trace_id"] == trace_id]
            if mine:
                return mine[-1]
            time.sleep(0.1)
        self.fail(f"no CONNECT row logged for trace {trace_id}")

    def connect(self, dest, trace=None, headers=None):
        """Raw CONNECT; returns (socket, status, response_headers)."""
        sock = socket.create_connection(("127.0.0.1", self.proxy_port), timeout=5)
        lines = [f"CONNECT {dest} HTTP/1.1", f"Host: {dest}"]
        if trace:
            lines.append(f"X-Trace-Id: {trace}")
        for key, value in (headers or {}).items():
            lines.append(f"{key}: {value}")
        sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        raw = b""
        while b"\r\n\r\n" not in raw:
            chunk = sock.recv(65536)
            self.assertTrue(chunk)
            raw += chunk
        head = raw.split(b"\r\n\r\n", 1)[0].decode(errors="replace")
        status = int(head.split()[1])
        resp_headers = {}
        for line in head.split("\r\n")[1:]:
            if ": " in line:
                key, value = line.split(": ", 1)
                resp_headers[key.lower()] = value
        return sock, status, resp_headers

    def test_tunnel_forwards_bytes_and_logs_metadata_only(self):
        payload = b"SECRET_TUNNEL_PAYLOAD_12345"
        sock, status, headers = self.connect(
            self.dest, trace="trace-connect-1",
            headers={"Authorization": "Bearer [REDACTED]"})
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("x-trace-id"), "trace-connect-1")
        sock.sendall(payload)
        received = b""
        while len(received) < len(payload):
            chunk = sock.recv(65536)
            self.assertTrue(chunk)
            received += chunk
        self.assertEqual(received, payload)
        sock.close()

        row = self.wait_row("trace-connect-1")
        self.assertEqual(row["method"], "CONNECT")
        self.assertEqual(row["endpoint"], self.dest)
        self.assertEqual(row["dest_host"], self.dest)
        self.assertEqual(row["status"], "success")
        self.assertGreaterEqual(row["bytes_in"], len(payload))
        self.assertGreaterEqual(row["bytes_out"], len(payload))
        self.assertGreaterEqual(row["latency_seconds"], 0)

        dump = "\n".join(str(r) for r in self.rows())
        self.assertNotIn("SECRET_TUNNEL_PAYLOAD_12345", dump)
        self.assertNotIn("SECRET_KEY_67890", dump)
        self.assertNotIn("Authorization", dump)

    def test_generated_trace_returned_and_failed_tunnel_logged(self):
        sock, status, headers = self.connect(self.dest)
        self.assertEqual(status, 200)
        generated = headers.get("x-trace-id")
        self.assertTrue(generated)
        sock.close()
        self.assertEqual(self.wait_row(generated)["status"], "success")

        tmp = socket.socket()
        tmp.bind(("127.0.0.1", 0))
        closed_port = tmp.getsockname()[1]
        tmp.close()
        sock, status, _ = self.connect(
            f"127.0.0.1:{closed_port}", trace="trace-connect-fail")
        self.assertEqual(status, 502)
        sock.close()
        row = self.wait_row("trace-connect-fail")
        self.assertEqual((row["method"], row["status"]), ("CONNECT", "failure"))
        self.assertEqual((row["bytes_in"], row["bytes_out"]), (0, 0))


if __name__ == "__main__":
    unittest.main()
