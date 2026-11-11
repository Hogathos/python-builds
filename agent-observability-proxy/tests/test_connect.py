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

# urllib honors NO_PROXY and would bypass the loopback test proxy;
# drop it so the suite never depends on ambient proxy config (N7).
os.environ.pop("NO_PROXY", None); os.environ.pop("no_proxy", None)

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


    def test_idle_tunnel_times_out_and_logs_failure(self):
        tmp = tempfile.TemporaryDirectory()
        db_path = os.path.join(tmp.name, "idle.db")
        proxy = proxy_module.serve(
            "127.0.0.1", 0, db_path, relay_timeout=0.3)
        port = proxy.server_address[1]
        threading.Thread(target=proxy.serve_forever, daemon=True).start()
        try:
            sock = socket.create_connection(("127.0.0.1", port), timeout=5)
            sock.sendall(
                f"CONNECT {self.dest} HTTP/1.1\r\nHost: {self.dest}\r\n"
                "X-Trace-Id: trace-idle-t5\r\n\r\n".encode())
            raw = b""
            while b"\r\n\r\n" not in raw:
                chunk = sock.recv(65536)
                self.assertTrue(chunk)
                raw += chunk
            self.assertEqual(int(raw.split(b"\r\n", 1)[0].split()[1]), 200)
            try:
                self.assertEqual(sock.recv(65536), b"")
            except socket.timeout:
                self.fail("idle tunnel never closed")
            sock.close()
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            rows = [r for r in conn.execute("SELECT * FROM attempts")
                    if r["trace_id"] == "trace-idle-t5"]
            conn.close()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "failure")
            self.assertEqual((rows[0]["bytes_in"], rows[0]["bytes_out"]), (0, 0))
        finally:
            proxy.shutdown()
            proxy.server_close()
            proxy.state.conn.close()
            tmp.cleanup()

    def test_tunnel_idle_under_configured_relay_timeout_survives_and_forwards(self):
        configured_relay_timeout_seconds = 2.0
        idle_duration_seconds = 1.0
        payload_sent_after_idle = b"payload-sent-after-idle-period"
        temporary_directory = tempfile.TemporaryDirectory()
        database_path = os.path.join(
            temporary_directory.name, "idle-under-relay-timeout.db")
        proxy_with_configured_relay_timeout = proxy_module.serve(
            "127.0.0.1", 0, database_path,
            relay_timeout=configured_relay_timeout_seconds)
        self.assertEqual(
            proxy_with_configured_relay_timeout.state.relay_timeout,
            configured_relay_timeout_seconds)
        proxy_port_with_configured_relay_timeout = (
            proxy_with_configured_relay_timeout.server_address[1])
        threading.Thread(
            target=proxy_with_configured_relay_timeout.serve_forever,
            daemon=True).start()
        try:
            tunnel_socket = socket.create_connection(
                ("127.0.0.1", proxy_port_with_configured_relay_timeout),
                timeout=5)
            tunnel_socket.sendall(
                f"CONNECT {self.dest} HTTP/1.1\r\nHost: {self.dest}\r\n"
                "X-Trace-Id: trace-idle-under-relay-timeout\r\n\r\n".encode())
            response_head = b""
            while b"\r\n\r\n" not in response_head:
                response_chunk = tunnel_socket.recv(65536)
                self.assertTrue(response_chunk)
                response_head += response_chunk
            self.assertEqual(
                int(response_head.split(b"\r\n", 1)[0].split()[1]), 200)
            # Idle for less than the configured timeout: the tunnel must
            # still be open afterwards, and must still forward bytes.
            time.sleep(idle_duration_seconds)
            tunnel_socket.sendall(payload_sent_after_idle)
            received_after_idle = b""
            while len(received_after_idle) < len(payload_sent_after_idle):
                received_chunk = tunnel_socket.recv(65536)
                self.assertTrue(received_chunk)
                received_after_idle += received_chunk
            self.assertEqual(received_after_idle, payload_sent_after_idle)
            tunnel_socket.close()
            logged_row = None
            for _ in range(50):
                connection = sqlite3.connect(database_path)
                connection.row_factory = sqlite3.Row
                matching_rows = [
                    row for row in connection.execute(
                        "SELECT * FROM attempts")
                    if row["trace_id"] == "trace-idle-under-relay-timeout"]
                connection.close()
                if matching_rows:
                    logged_row = matching_rows[-1]
                    break
                time.sleep(0.1)
            self.assertIsNotNone(logged_row)
            self.assertEqual(logged_row["status"], "success")
            self.assertGreaterEqual(
                logged_row["bytes_in"], len(payload_sent_after_idle))
            self.assertGreaterEqual(
                logged_row["bytes_out"], len(payload_sent_after_idle))
            self.assertGreaterEqual(
                logged_row["latency_seconds"], idle_duration_seconds)
        finally:
            proxy_with_configured_relay_timeout.shutdown()
            proxy_with_configured_relay_timeout.server_close()
            proxy_with_configured_relay_timeout.state.conn.close()
            temporary_directory.cleanup()


if __name__ == "__main__":
    unittest.main()
