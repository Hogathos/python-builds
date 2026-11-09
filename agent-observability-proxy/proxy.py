"""M1+M2: local forwarding proxy on 127.0.0.1:8888.

M1: forwards plain-HTTP requests to their real destination.
M2: accepts CONNECT, establishes a raw TCP tunnel, and relays bytes
both ways so HTTPS can pass through. The tunnel is never decrypted:
no TLS interception, no MITM. Only tunnel metadata is logged (see
db.py) - destination, timing, byte counts, result - never payload
content, headers, keys, or bodies.

M3: the trace ID above is carried across two agents (A -> proxy
-> B -> proxy -> upstream) with no change to M1/M2 behaviour; both
legs log under the same trace_id, distinguished by dest/endpoint.
M4: allowlist + rate limit. Only destinations on the configurable
allowlist (default: local test hosts 127.0.0.1 / localhost / ::1)
are forwarded. Anything else is blocked at the proxy (HTTP 403,
CONNECT tunnel never opened) and logged outcome=blocked,
reason=not_allowlisted. More than RATE_LIMIT requests to one
destination inside RATE_WINDOW_SECONDS gets 429, is logged
outcome=rate_limited, reason=rate_limited, and is never forwarded;
after the window passes, requests pass again. Blocked and
rate-limited attempts still log trace, destination, method, status,
and latency, with zero forwarded bytes. No TLS decryption (as M2).

Trace ID: an incoming X-Trace-Id is forwarded unchanged; if absent one
is generated, added to the upstream request, and returned to the client
in the X-Trace-Id response header.

Never logged: Authorization / API-key headers and request/response
bodies. Token counts are recorded only when the upstream JSON response
itself reports `usage`; cost is never invented (stays 0.0).
"""
from __future__ import annotations

import argparse
import http.client
import json
import select
import socket
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import db as db_module

# M4 policy defaults (configurable via serve()/CLI).
DEFAULT_ALLOWLIST = ("127.0.0.1", "localhost", "::1")
RATE_LIMIT = 100            # max forwarded requests per destination ...
RATE_WINDOW_SECONDS = 10.0  # ... inside this sliding window

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-connection", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade",
}


def _usage_input_tokens(body: bytes, content_type: str) -> int:
    """Tokens only if the API response itself reports usage; else 0."""
    if "json" not in (content_type or "").lower():
        return 0
    try:
        payload = json.loads(body.decode("utf-8", errors="strict"))
    except Exception:
        return 0
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        return 0
    for key in ("input_tokens", "prompt_tokens"):
        value = usage.get(key)
        if isinstance(value, int):
            return value
    return 0


class ProxyState:
    def __init__(self, db_path: str, retry_window: float = 10.0,
                 allowlist=None, rate_limit: int = RATE_LIMIT,
                 rate_window: float = RATE_WINDOW_SECONDS):
        self.conn = db_module.init_db(db_path)
        self.retry_window = retry_window
        self.allowlist = tuple(
            entry.strip().lower() for entry in
            (allowlist if allowlist is not None else DEFAULT_ALLOWLIST)
            if entry.strip())
        self.rate_limit = int(rate_limit)
        self.rate_window = float(rate_window)
        self._lock = threading.Lock()
        self._task_by_trace: dict[str, int] = {}
        self._next_task = 1
        self._attempts: dict[tuple[str, str, str], list[float]] = {}
        self._rate_stamps: dict[str, list[float]] = {}

    def is_allowed(self, dest_host: str, dest_port: int) -> bool:
        """Allowlist entries are hosts, or host:port for one exact port.

        A bare host (IPv4, hostname, or IPv6 with or without brackets)
        matches on any port. A host:port entry matches only that exact
        port; IPv6 host:port must use brackets ([::1]:18080).
        """
        host = dest_host.strip().lower()
        if host.startswith("[") and host.endswith("]"):
            host = host[1:-1]
        for entry in self.allowlist:
            if entry.startswith("["):
                if "]:" in entry:
                    ehost, _, eport = entry[1:].partition("]:")
                    try:
                        if ehost == host and int(eport) == dest_port:
                            return True
                    except ValueError:
                        continue
                elif entry.endswith("]"):
                    if entry[1:-1] == host:
                        return True
            elif entry.count(":") == 1:
                if entry == f"{host}:{dest_port}":
                    return True
            elif entry == host:
                return True
        return False

    def check_rate(self, dest_label: str) -> bool:
        """Sliding window per destination; True = this request may pass."""
        now = time.time()
        with self._lock:
            stamps = [s for s in self._rate_stamps.get(dest_label, [])
                      if now - s <= self.rate_window]
            if len(stamps) >= self.rate_limit:
                self._rate_stamps[dest_label] = stamps
                return False
            stamps.append(now)
            self._rate_stamps[dest_label] = stamps
            return True

    def task_number(self, trace_id: str, explicit: str | None) -> int:
        if explicit:
            try:
                return int(explicit)
            except ValueError:
                pass
        with self._lock:
            if trace_id not in self._task_by_trace:
                self._task_by_trace[trace_id] = self._next_task
                self._next_task += 1
            return self._task_by_trace[trace_id]

    def next_attempt(self, trace_id: str, endpoint: str, method: str) -> int:
        # Retry grouping: same trace_id + endpoint + method in window.
        now = time.time()
        key = (trace_id, endpoint, method)
        with self._lock:
            stamps = [t for t in self._attempts.get(key, [])
                      if now - t <= self.retry_window]
            stamps.append(now)
            self._attempts[key] = stamps
            return len(stamps)


def _relay(client: socket.socket, upstream: socket.socket) -> tuple[int, int]:
    """Relay raw bytes both ways; return (bytes_in, bytes_out).

    Bytes are counted, never inspected, stored, or logged. bytes_in is
    client -> destination, bytes_out is destination -> client.
    """
    bytes_in = bytes_out = 0
    sockets = [client, upstream]
    while True:
        readable, _, _ = select.select(sockets, [], [])
        for sock in readable:
            data = sock.recv(65536)
            if not data:
                return bytes_in, bytes_out
            if sock is client:
                upstream.sendall(data)
                bytes_in += len(data)
            else:
                client.sendall(data)
                bytes_out += len(data)


def make_handler(state: ProxyState):
    class ProxyHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # keep stdout clean
            pass

        # -- M2: CONNECT tunnelling, bytes only, never decrypted. -----
        def do_CONNECT(self):
            start = time.perf_counter()
            trace_id = self.headers.get("X-Trace-Id") or str(uuid.uuid4())
            endpoint = self.path  # CONNECT authority form: host:port
            if ":" in endpoint:
                dest_host, port_text = endpoint.rsplit(":", 1)
                try:
                    dest_port = int(port_text)
                except ValueError:
                    dest_port = -1
            else:
                dest_host, dest_port = endpoint, 443
            endpoint = f"{dest_host}:{dest_port}"
            task_number = state.task_number(
                trace_id, self.headers.get("X-Task-Number"))
            attempt = state.next_attempt(trace_id, endpoint, "CONNECT")
            strategy = self.headers.get("X-Strategy") or "proxy"

            def log_tunnel(status, bytes_in, bytes_out):
                db_module.log_attempt(
                    state.conn, trace_id=trace_id,
                    task_number=task_number, attempt=attempt,
                    strategy=strategy, status=status,
                    latency_seconds=time.perf_counter() - start,
                    retry_reason="retry" if attempt > 1 else "",
                    dest_host=endpoint, endpoint=endpoint,
                    method="CONNECT", bytes_in=bytes_in,
                    bytes_out=bytes_out, http_status=None,
                    outcome="allowed", reason="")

            if not state.is_allowed(dest_host, dest_port):
                db_module.log_attempt(
                    state.conn, trace_id=trace_id,
                    task_number=task_number, attempt=attempt,
                    strategy=strategy, status="blocked",
                    latency_seconds=time.perf_counter() - start,
                    retry_reason="retry" if attempt > 1 else "",
                    dest_host=endpoint, endpoint=endpoint,
                    method="CONNECT", bytes_in=0, bytes_out=0,
                    http_status=403, outcome="blocked",
                    reason="not_allowlisted")
                self.send_response(403)
                self.send_header("X-Trace-Id", trace_id)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if not state.check_rate(endpoint):
                db_module.log_attempt(
                    state.conn, trace_id=trace_id,
                    task_number=task_number, attempt=attempt,
                    strategy=strategy, status="rate_limited",
                    latency_seconds=time.perf_counter() - start,
                    retry_reason="retry" if attempt > 1 else "",
                    dest_host=endpoint, endpoint=endpoint,
                    method="CONNECT", bytes_in=0, bytes_out=0,
                    http_status=429, outcome="rate_limited",
                    reason="rate_limited")
                self.send_response(429)
                self.send_header("X-Trace-Id", trace_id)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            upstream = None
            try:
                upstream = socket.create_connection(
                    (dest_host, dest_port), timeout=10)
            except Exception:
                self.send_response(502)
                self.send_header("X-Trace-Id", trace_id)
                self.send_header("Content-Length", "0")
                self.end_headers()
                log_tunnel("failure", 0, 0)
                return

            self.send_response(200)
            self.send_header("X-Trace-Id", trace_id)
            self.end_headers()
            self.wfile.flush()
            self.close_connection = True
            status, bytes_in, bytes_out = "success", 0, 0
            try:
                bytes_in, bytes_out = _relay(self.connection, upstream)
            except Exception:
                status = "failure"
            finally:
                upstream.close()
            log_tunnel(status, bytes_in, bytes_out)

        def _target(self):
            """Return (host, port, endpoint), None if unsupported.

            Raises ValueError when the destination is malformed (bad
            port); the caller answers 400 and logs a row.
            """
            parsed = urlparse(self.path)
            if parsed.scheme in ("http", "https") and parsed.hostname:
                if parsed.scheme != "http":
                    return None
                endpoint = parsed.path or "/"
                if parsed.query:
                    endpoint += "?" + parsed.query
                return parsed.hostname, parsed.port or 80, endpoint
            host_header = self.headers.get("Host", "")
            if not host_header:
                return None
            if ":" in host_header:
                host, port = host_header.rsplit(":", 1)
                return host, int(port), self.path
            return host_header, 80, self.path

        def _reject_malformed_header(self, state, trace_id, start):
            """400 plus an audit row for an unparseable destination."""
            task_number = state.task_number(
                trace_id, self.headers.get("X-Task-Number"))
            attempt = state.next_attempt(trace_id, self.path, self.command)
            strategy = self.headers.get("X-Strategy") or "proxy"
            body = b"failure: request not forwarded by proxy\n"
            db_module.log_attempt(
                state.conn, trace_id=trace_id,
                task_number=task_number, attempt=attempt,
                strategy=strategy, status="failure",
                latency_seconds=time.perf_counter() - start,
                retry_reason="retry" if attempt > 1 else "",
                dest_host=self.headers.get("Host") or "",
                endpoint=self.path,
                method=self.command, bytes_in=0, bytes_out=0,
                http_status=400, outcome="failure",
                reason="malformed_header")
            self.send_response(400)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Trace-Id", trace_id)
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

        def _handle(self):
            start = time.perf_counter()
            trace_id = self.headers.get("X-Trace-Id") or str(uuid.uuid4())
            try:
                target = self._target()
            except ValueError:
                self._reject_malformed_header(state, trace_id, start)
                return
            if target is None:
                body = b"Only absolute http:// URLs are supported in M1\n"
                self.send_response(501)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("X-Trace-Id", trace_id)
                self.end_headers()
                self.wfile.write(body)
                return

            dest_host, dest_port, endpoint = target
            dest_label = (dest_host if dest_port == 80
                          else f"{dest_host}:{dest_port}")
            task_number = state.task_number(
                trace_id, self.headers.get("X-Task-Number"))
            attempt = state.next_attempt(trace_id, endpoint, self.command)
            strategy = self.headers.get("X-Strategy") or "proxy"

            def reject(code, status, reason):
                body = f"{status}: request not forwarded by proxy\n".encode()
                db_module.log_attempt(
                    state.conn, trace_id=trace_id,
                    task_number=task_number, attempt=attempt,
                    strategy=strategy, status=status,
                    latency_seconds=time.perf_counter() - start,
                    retry_reason="retry" if attempt > 1 else "",
                    dest_host=dest_label, endpoint=endpoint,
                    method=self.command, bytes_in=0, bytes_out=0,
                    http_status=code, outcome=status, reason=reason)
                self.send_response(code)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("X-Trace-Id", trace_id)
                self.end_headers()
                self.wfile.write(body)
                self.close_connection = True

            if not state.is_allowed(dest_host, dest_port):
                reject(403, "blocked", "not_allowlisted")
                return
            if not state.check_rate(dest_label):
                reject(429, "rate_limited", "rate_limited")
                return

            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                reject(400, "failure", "malformed_header")
                return
            request_body = self.rfile.read(length) if length else b""

            headers = {}
            for key, value in self.headers.items():
                if key.lower() in HOP_BY_HOP or key.lower() == "host":
                    continue
                headers[key] = value  # forwarded, never logged
            headers["Host"] = dest_label
            headers["X-Trace-Id"] = trace_id

            status, http_status, response_body, resp_headers = "error", 502, b"", {}
            try:
                upstream = http.client.HTTPConnection(
                    dest_host, dest_port, timeout=10)
                upstream.request(self.command, endpoint,
                                 body=request_body or None, headers=headers)
                resp = upstream.getresponse()
                response_body = resp.read()
                http_status = resp.status
                status = "success" if 200 <= http_status < 400 else "failure"
                resp_headers = dict(resp.getheaders())
                upstream.close()
            except Exception:
                response_body = b"Bad Gateway\n"

            latency = time.perf_counter() - start
            input_tokens = _usage_input_tokens(
                response_body, resp_headers.get("Content-Type", ""))
            db_module.log_attempt(
                state.conn,
                trace_id=trace_id,
                task_number=task_number,
                attempt=attempt,
                strategy=strategy,
                status=status,
                latency_seconds=latency,
                input_tokens=input_tokens,
                cost_dollars=0.0,
                retry_reason="retry" if attempt > 1 else "",
                dest_host=dest_label,
                endpoint=endpoint,
                method=self.command,
                bytes_in=len(request_body),
                bytes_out=len(response_body),
                http_status=http_status,
                outcome="allowed",
                reason="",
            )

            self.send_response(http_status)
            for key, value in resp_headers.items():
                if key.lower() in HOP_BY_HOP or key.lower() == "content-length":
                    continue
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(response_body)))
            self.send_header("X-Trace-Id", trace_id)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(response_body)

        do_GET = _handle
        do_POST = _handle
        do_PUT = _handle
        do_PATCH = _handle
        do_DELETE = _handle
        do_HEAD = _handle
        do_OPTIONS = _handle

    return ProxyHandler


def serve(host: str = "127.0.0.1", port: int = 8888,
          db_path: str = "attempts.db", allowlist=None,
          rate_limit: int = RATE_LIMIT,
          rate_window: float = RATE_WINDOW_SECONDS) -> ThreadingHTTPServer:
    state = ProxyState(db_path, allowlist=allowlist,
                       rate_limit=rate_limit, rate_window=rate_window)
    server = ThreadingHTTPServer((host, port), make_handler(state))
    server.state = state  # type: ignore[attr-defined]
    return server


def main():
    parser = argparse.ArgumentParser(description="M1-M4 local proxy (HTTP + CONNECT + allowlist/rate limit)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8888)
    parser.add_argument("--db", default="attempts.db")
    parser.add_argument("--allowlist", default=",".join(DEFAULT_ALLOWLIST),
                        help="comma-separated allowed hosts (or host:port)")
    parser.add_argument("--rate-limit", type=int, default=RATE_LIMIT)
    parser.add_argument("--rate-window", type=float,
                        default=RATE_WINDOW_SECONDS)
    args = parser.parse_args()
    server = serve(args.host, args.port, args.db,
                   allowlist=args.allowlist.split(","),
                   rate_limit=args.rate_limit, rate_window=args.rate_window)
    print(f"proxy listening on {args.host}:{args.port} db={args.db}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
