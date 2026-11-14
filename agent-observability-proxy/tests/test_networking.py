"""Networking fundamentals: streaming, chunked, IP forms, smuggling hygiene,
Upgrade/501, IPv6 parsing, and the trace fields (bytes_tx/rx, close_reason,
connect_ms/duration_ms, honest CONNECT rows, exact blocked host:port)."""
import http.client
import json
import os
import socket
import socketserver
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.pop("NO_PROXY", None); os.environ.pop("no_proxy", None)

import proxy as proxy_module
import server as server_module


class _StreamHandler(BaseHTTPRequestHandler):
    """SSE-style upstream: headers, one chunk, wait, second chunk, close."""
    protocol_version = "HTTP/1.1"
    gate = None

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()  # no length: close-delimited on purpose
        self.wfile.write(b"data: one\n\n")
        self.wfile.flush()
        self.gate.wait(timeout=10)
        self.wfile.write(b"data: two\n\n")
        self.wfile.flush()
        self.close_connection = True


class _ChunkEchoHandler(BaseHTTPRequestHandler):
    """Upstream that reads a chunked body itself and reports its size."""

    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def do_POST(self):
        total = -1
        if "chunked" in self.headers.get("Transfer-Encoding", "").lower():
            total = 0
            while True:
                line = self.rfile.readline(8192)
                size = int(line.split(b";")[0].strip(), 16)
                if size == 0:
                    break
                left = size
                while left:
                    block = self.rfile.read(left)
                    if not block:
                        break
                    total += len(block)
                    left -= len(block)
                self.rfile.read(2)
            while self.rfile.readline(8192).strip():
                pass
        body = json.dumps({"chunked_bytes": total}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True


class _EchoTCPHandler(socketserver.BaseRequestHandler):
    """Raw TCP echo end for CONNECT tunnel tests."""

    def handle(self):
        while True:
            data = self.request.recv(65536)
            if not data:
                return
            self.request.sendall(data)


class NetworkingFundamentalsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.tmp.name, "attempts.db")
        cls.upstream = ThreadingHTTPServer(
            ("127.0.0.1", 0), server_module.Handler)
        cls.upstream_port = cls.upstream.server_address[1]
        threading.Thread(target=cls.upstream.serve_forever,
                         daemon=True).start()
        cls.stream_gate = threading.Event()
        _StreamHandler.gate = cls.stream_gate
        cls.streamer = ThreadingHTTPServer(
            ("127.0.0.1", 0), _StreamHandler)
        cls.streamer_port = cls.streamer.server_address[1]
        threading.Thread(target=cls.streamer.serve_forever,
                         daemon=True).start()
        cls.chunked = ThreadingHTTPServer(
            ("127.0.0.1", 0), _ChunkEchoHandler)
        cls.chunked_port = cls.chunked.server_address[1]
        threading.Thread(target=cls.chunked.serve_forever,
                         daemon=True).start()
        cls.echo = socketserver.ThreadingTCPServer(
            ("127.0.0.1", 0), _EchoTCPHandler)
        cls.echo_port = cls.echo.server_address[1]
        threading.Thread(target=cls.echo.serve_forever, daemon=True).start()
        cls.proxy = proxy_module.serve("127.0.0.1", 0, cls.db_path)
        cls.proxy_port = cls.proxy.server_address[1]
        threading.Thread(target=cls.proxy.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.upstream_port}"

    @classmethod
    def tearDownClass(cls):
        cls.proxy.shutdown(); cls.upstream.shutdown()
        cls.streamer.shutdown(); cls.chunked.shutdown(); cls.echo.shutdown()
        for server in (cls.proxy, cls.upstream, cls.streamer,
                       cls.chunked, cls.echo):
            server.server_close()
        cls.proxy.state.conn.close()
        cls.tmp.cleanup()

    def rows(self, trace):
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        out = [r for r in conn.execute(
            "SELECT * FROM attempts ORDER BY id") if r["trace_id"] == trace]
        conn.close()
        return out

    def wait_rows(self, trace, count=1, timeout=10):
        """Streamed and relayed rows land after the client is done; wait."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            found = self.rows(trace)
            if len(found) >= count:
                return found
            time.sleep(0.1)
        return self.rows(trace)

    def raw(self, text):
        """One raw request through the proxy; returns (status, head, body)."""
        sock = socket.create_connection(
            ("127.0.0.1", self.proxy_port), timeout=10)
        sock.sendall(text.encode())
        raw = b""
        while b"\r\n\r\n" not in raw:
            chunk = sock.recv(65536)
            if not chunk:
                break
            raw += chunk
        head, _, rest = raw.partition(b"\r\n\r\n")
        status = int(head.split(b"\r\n", 1)[0].split()[1])
        headers = {}
        for line in head.decode(errors="replace").split("\r\n")[1:]:
            if ": " in line:
                key, value = line.split(": ", 1)
                headers[key.lower()] = value
        body = rest
        if "content-length" in headers:
            left = int(headers["content-length"]) - len(body)
            while left > 0:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                body += chunk
                left -= len(chunk)
        else:
            sock.settimeout(2)
            try:
                while True:
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    body += chunk
            except socket.timeout:
                pass
        sock.close()
        return status, headers, body

    # -- IP forms: every spelling of 127.0.0.1 is allowlisted. --

    def test_ip_spellings_normalize_to_loopback(self):
        cases = {
            "127.0.0.1": "127.0.0.1",
            "0x7f.0.0.1": "127.0.0.1",
            "2130706433": "127.0.0.1",
            "0177.0.0.1": "127.0.0.1",
            "127.1": "127.0.0.1",
            "::ffff:127.0.0.1": "127.0.0.1",
            "127.0.0.1.": "127.0.0.1",
            "LOCALHOST": "localhost",
            "Example.COM.": "example.com",
        }
        for raw, want in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(proxy_module._normalize_host(raw), want)

    def test_ip_spellings_allowed_non_loopback_blocked(self):
        state = self.proxy.state
        for raw in ("127.0.0.1", "0x7f.0.0.1", "2130706433", "0177.0.0.1",
                    "::ffff:127.0.0.1", "127.1", "127.0.0.1.", "LOCALHOST"):
            with self.subTest(raw=raw):
                self.assertTrue(state.is_allowed(raw, 18080))
        self.assertFalse(state.is_allowed("127.0.0.2", 18080))
        self.assertFalse(state.is_allowed("localhost.evil", 80))

    def test_allowlist_port_entry_with_ip_spelling(self):
        import sqlite3
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        state = proxy_module.ProxyState(
            os.path.join(tmp.name, "t.db"),
            allowlist=["0x7f.0.0.1:18080"])
        self.assertTrue(state.is_allowed("2130706433", 18080))
        self.assertFalse(state.is_allowed("2130706433", 18081))
        state.conn.close()

    # -- Authority parsing, including IPv6. --

    def test_split_authority(self):
        split = proxy_module._split_authority
        self.assertEqual(split("example.com", 80), ("example.com", 80))
        self.assertEqual(split("example.com:8080", 80), ("example.com", 8080))
        self.assertEqual(split("[::1]:8080", 80), ("::1", 8080))
        self.assertEqual(split("[::1]", 80), ("::1", 80))
        self.assertEqual(split("::1", 80), ("::1", 80))
        self.assertEqual(split("fe80::1", 443), ("fe80::1", 443))
        for bad in ("example.com:abc", "example.com:", "[::1",
                    "[::1]x8080", "example.com:99999"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    split(bad, 80)

    def test_ipv6_bracketed_host_header_reaches_allowlist(self):
        # Origin-form: the Host header is the only destination source.
        status, headers, _ = self.raw(
            "GET /echo HTTP/1.1\r\n"
            f"Host: [::1]:{self.upstream_port}\r\n"
            "X-Trace-Id: trace-ipv6-bracket\r\n\r\n")
        row = self.rows("trace-ipv6-bracket")[-1]
        self.assertEqual(row["dest_host"], f"[::1]:{self.upstream_port}")

    # -- Smuggling hygiene: duplicates, mixed framing, caps. --

    def test_duplicate_content_length_rejected(self):
        status, headers, body = self.raw(
            f"POST {self.base}/echo HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{self.upstream_port}\r\n"
            "Content-Length: 0\r\nContent-Length: 0\r\n"
            "X-Trace-Id: trace-dup-cl\r\n\r\n")
        self.assertEqual(status, 400)
        self.assertEqual(headers.get("x-trace-id"), "trace-dup-cl")
        row = self.rows("trace-dup-cl")[-1]
        self.assertEqual(row["reason"], "duplicate_content_length")
        self.assertEqual(row["http_status"], 400)
        self.assertEqual(row["close_reason"], "unknown")
        self.assertNotIn("SECRET", body.decode())

    def test_content_length_plus_chunked_rejected(self):
        status, _, _ = self.raw(
            f"POST {self.base}/echo HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{self.upstream_port}\r\n"
            "Content-Length: 5\r\nTransfer-Encoding: chunked\r\n"
            "X-Trace-Id: trace-cl-te\r\n\r\n0\r\n\r\n")
        self.assertEqual(status, 400)
        row = self.rows("trace-cl-te")[-1]
        self.assertEqual(row["reason"], "content_length_with_transfer_encoding")

    def test_oversize_body_rejected_with_413(self):
        status, headers, body = self.raw(
            f"POST {self.base}/echo HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{self.upstream_port}\r\n"
            "Content-Length: 99999999\r\n"
            "X-Trace-Id: trace-big-1\r\n\r\n")
        self.assertEqual(status, 413)
        self.assertEqual(headers.get("x-trace-id"), "trace-big-1")
        row = self.rows("trace-big-1")[-1]
        self.assertEqual(row["reason"], "body_too_big")
        self.assertEqual(row["http_status"], 413)
        self.assertIn("too big", body.decode())

    # -- Upgrade and unknown methods: plain-words 501 plus a row. --

    def test_upgrade_on_plain_http_needs_connect(self):
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.proxy_port, timeout=10)
        conn.request("GET", f"{self.base}/echo",
                     headers={"Upgrade": "websocket",
                              "X-Trace-Id": "trace-upgrade-1"})
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        self.assertEqual(resp.status, 501)
        self.assertIn("CONNECT", body.decode())
        row = self.rows("trace-upgrade-1")[-1]
        self.assertEqual(row["reason"], "upgrade_needs_connect")
        self.assertEqual(row["http_status"], 501)

    def test_unimplemented_method_logged_not_silent(self):
        status, headers, body = self.raw(
            f"FROB {self.base}/echo HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{self.upstream_port}\r\n"
            "X-Trace-Id: trace-frob-1\r\n\r\n")
        self.assertEqual(status, 501)
        self.assertEqual(headers.get("x-trace-id"), "trace-frob-1")
        self.assertIn("FROB", body.decode())
        row = self.rows("trace-frob-1")[-1]
        self.assertEqual(row["method"], "FROB")
        self.assertEqual(row["reason"], "unimplemented_method")
        self.assertEqual(row["http_status"], 501)

    # -- Chunked requests reach the upstream intact. --

    def test_chunked_request_forwarded(self):
        sock = socket.create_connection(
            ("127.0.0.1", self.proxy_port), timeout=10)
        payload = b"hello-chunked-world"
        sock.sendall(
            f"POST http://127.0.0.1:{self.chunked_port}/echo HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{self.chunked_port}\r\n"
            "Transfer-Encoding: chunked\r\n"
            "Content-Type: text/plain\r\n"
            "X-Trace-Id: trace-chunked-1\r\n\r\n"
            f"{len(payload):X}\r\n".encode() + payload + b"\r\n0\r\n\r\n")
        raw = b""
        while b"\r\n\r\n" not in raw:
            raw += sock.recv(65536)
        head, _, rest = raw.partition(b"\r\n\r\n")
        status = int(head.split(b"\r\n", 1)[0].split()[1])
        length = None
        for line in head.decode().split("\r\n")[1:]:
            if line.lower().startswith("content-length:"):
                length = int(line.split(":")[1])
        while len(rest) < length:
            rest += sock.recv(65536)
        sock.close()
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(rest)["chunked_bytes"], len(payload))
        row = self.rows("trace-chunked-1")[-1]
        self.assertEqual(row["status"], "success")
        self.assertEqual(row["bytes_tx"], len(payload))
        self.assertGreater(row["bytes_rx"], 0)
        self.assertEqual(row["bytes_in"], len(payload))
        self.assertEqual(row["close_reason"], "success")

    # -- Streaming: the first chunk arrives before the upstream is done. --

    def test_sse_first_chunk_streams_before_upstream_finishes(self):
        self.stream_gate.clear()
        sock = socket.create_connection(
            ("127.0.0.1", self.proxy_port), timeout=10)
        sock.sendall((
            f"GET http://127.0.0.1:{self.streamer_port}/stream HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{self.streamer_port}\r\n"
            "X-Trace-Id: trace-stream-1\r\n\r\n").encode())
        raw = b""
        while b"\r\n\r\n" not in raw:
            raw += sock.recv(65536)
        head, _, rest = raw.partition(b"\r\n\r\n")
        status = int(head.split(b"\r\n", 1)[0].split()[1])
        self.assertEqual(status, 200)
        # The upstream is still parked on the gate: anything we already
        # hold arrived by streaming, not by whole-body buffering.
        sock.settimeout(5)
        while b"data: one" not in rest:
            chunk = sock.recv(65536)
            if not chunk:  # closed without the chunk: fail loudly, never spin
                break
            rest += chunk
        self.assertFalse(self.stream_gate.is_set())
        self.stream_gate.set()
        sock.settimeout(5)
        try:
            while b"data: two" not in rest:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                rest += chunk
        except socket.timeout:
            pass
        sock.close()
        self.assertIn(b"data: one", rest)
        self.assertIn(b"data: two", rest)
        row = self.wait_rows("trace-stream-1")[-1]
        self.assertEqual(row["status"], "success")
        self.assertEqual(row["bytes_rx"], len(rest))
        self.assertEqual(row["close_reason"], "success")

    # -- Trace fields on plain rows. --

    def test_success_row_carries_tx_rx_timing_and_reason(self):
        data = b'{"probe": 1}'
        req = urllib.request.Request(
            self.base + "/echo", data=data, method="POST",
            headers={"Content-Type": "application/json"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler(
            {"http": f"http://127.0.0.1:{self.proxy_port}"}))
        trace = "trace-fields-1"
        req.add_header("X-Trace-Id", trace)
        with opener.open(req, timeout=10) as resp:
            body = resp.read()
        self.assertEqual(resp.status, 200)
        row = self.rows(trace)[-1]
        self.assertEqual(row["status"], "success")
        self.assertEqual(row["close_reason"], "success")
        self.assertEqual(row["bytes_tx"], len(data))
        self.assertEqual(row["bytes_rx"], len(body))
        self.assertEqual(row["bytes_in"], len(data))
        self.assertIsNotNone(row["connect_ms"])
        self.assertGreaterEqual(row["connect_ms"], 0)
        self.assertIsNotNone(row["duration_ms"])
        self.assertGreaterEqual(row["duration_ms"], row["connect_ms"])

    def test_refused_upstream_logs_upstream_reset(self):
        dead = socket.socket()
        dead.bind(("127.0.0.1", 0))
        port = dead.getsockname()[1]
        dead.close()
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.proxy_port, timeout=10)
        conn.request("GET", f"http://127.0.0.1:{port}/echo",
                     headers={"X-Trace-Id": "trace-reset-1"})
        resp = conn.getresponse()
        resp.read()
        conn.close()
        self.assertEqual(resp.status, 502)
        row = self.rows("trace-reset-1")[-1]
        self.assertEqual(row["close_reason"], "upstream_reset")
        self.assertEqual(row["http_status"], 502)
        self.assertIsNotNone(row["connect_ms"])

    def test_blocked_row_names_exact_host_port(self):
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.proxy_port, timeout=10)
        conn.request("GET", "http://10.9.9.9:1234/echo",
                     headers={"X-Trace-Id": "trace-blocked-port"})
        resp = conn.getresponse()
        resp.read()
        conn.close()
        self.assertEqual(resp.status, 403)
        row = self.rows("trace-blocked-port")[-1]
        self.assertEqual(row["dest_host"], "10.9.9.9:1234")
        self.assertEqual(row["outcome"], "blocked")
        self.assertEqual(row["close_reason"], "blocked_allowlist")

    def test_rate_limited_row_carries_reason(self):
        tmp = tempfile.TemporaryDirectory()
        limited = proxy_module.serve(
            "127.0.0.1", 0, os.path.join(tmp.name, "limited.db"),
            rate_limit=1, rate_window=60)
        port = limited.server_address[1]
        threading.Thread(target=limited.serve_forever, daemon=True).start()
        # Cleanups run last-added first, so add them in reverse stop order.
        self.addCleanup(tmp.cleanup)
        self.addCleanup(limited.state.conn.close)
        self.addCleanup(limited.server_close)
        self.addCleanup(limited.shutdown)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler(
            {"http": f"http://127.0.0.1:{port}"}))

        def get(trace):
            req = urllib.request.Request(self.base + "/echo")
            req.add_header("X-Trace-Id", trace)
            try:
                with opener.open(req, timeout=10) as resp:
                    return resp.status
            except urllib.error.HTTPError as err:
                return err.code

        self.assertEqual(get("trace-limit-1"), 200)
        self.assertEqual(get("trace-limit-2"), 429)
        import sqlite3
        conn = sqlite3.connect(os.path.join(tmp.name, "limited.db"))
        conn.row_factory = sqlite3.Row
        rows = [r for r in conn.execute("SELECT * FROM attempts")
                if r["trace_id"] == "trace-limit-2"]
        conn.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["outcome"], "rate_limited")
        self.assertEqual(rows[0]["close_reason"], "rate_limited")

    # -- CONNECT honesty: one row per tunnel, tunnel fields. --

    def test_connect_tunnel_is_one_honest_row(self):
        payload = b"tunnel-bytes-12345"
        sock = socket.create_connection(
            ("127.0.0.1", self.proxy_port), timeout=10)
        dest = f"127.0.0.1:{self.echo_port}"
        sock.sendall(
            f"CONNECT {dest} HTTP/1.1\r\nHost: {dest}\r\n"
            "X-Trace-Id: trace-tunnel-1\r\n\r\n".encode())
        raw = b""
        while b"\r\n\r\n" not in raw:
            raw += sock.recv(65536)
        self.assertEqual(int(raw.split(b"\r\n", 1)[0].split()[1]), 200)
        sock.sendall(payload)
        echoed = b""
        while len(echoed) < len(payload):
            echoed += sock.recv(65536)
        self.assertEqual(echoed, payload)
        sock.close()
        rows = self.wait_rows("trace-tunnel-1")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["method"], "CONNECT")
        self.assertEqual(row["endpoint"], dest)
        self.assertEqual(row["dest_host"], dest)
        self.assertEqual(row["status"], "success")
        self.assertEqual(row["close_reason"], "success")
        self.assertGreaterEqual(row["bytes_tx"], len(payload))
        self.assertGreaterEqual(row["bytes_rx"], len(payload))
        self.assertIsNotNone(row["connect_ms"])
        self.assertGreaterEqual(
            row["duration_ms"], row["connect_ms"])

    # -- The dashboard API exposes the new fields. --

    def test_trace_api_exposes_new_fields(self):
        import api as api_module
        old_path = api_module.DB_PATH
        api_module.DB_PATH = self.db_path
        self.addCleanup(setattr, api_module, "DB_PATH", old_path)
        traces = api_module.list_traces()["traces"]
        by_trace = {t["trace_id"]: t for t in traces}
        self.assertIn("trace-chunked-1", by_trace)
        for key in ("bytes_tx", "bytes_rx", "close_reason",
                    "connect_ms", "duration_ms"):
            self.assertIn(key, by_trace["trace-chunked-1"])
        self.assertIn("tunnels", by_trace["trace-tunnel-1"])
        self.assertEqual(by_trace["trace-tunnel-1"]["tunnels"], 1)
        detail = api_module.get_trace("trace-chunked-1")
        for key in ("bytes_tx", "bytes_rx", "close_reason",
                    "connect_ms", "duration_ms"):
            self.assertIn(key, detail["attempts"][0])
        tunnels = [t for t in traces
                   if t["method"] == "CONNECT"]
        self.assertTrue(tunnels)


if __name__ == "__main__":
    unittest.main()
