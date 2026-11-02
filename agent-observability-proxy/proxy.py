"""M1: local HTTP forwarding proxy on 127.0.0.1:8888.

Forwards plain-HTTP requests to their real destination and logs one
metadata-only row per request to the SQLite `attempts` table (see db.py).

M1 scope only: no CONNECT tunnelling, no TLS decryption, no allowlist,
no rate limiting. CONNECT and absolute-https requests get 501.

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
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import db as db_module

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
    def __init__(self, db_path: str, retry_window: float = 10.0):
        self.conn = db_module.init_db(db_path)
        self.retry_window = retry_window
        self._lock = threading.Lock()
        self._task_by_trace: dict[str, int] = {}
        self._next_task = 1
        self._attempts: dict[tuple[str, str], list[float]] = {}

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
        # Retry grouping per sketch: same trace_id + endpoint in window.
        now = time.time()
        key = (trace_id, endpoint)
        with self._lock:
            stamps = [t for t in self._attempts.get(key, [])
                      if now - t <= self.retry_window]
            stamps.append(now)
            self._attempts[key] = stamps
            return len(stamps)


def make_handler(state: ProxyState):
    class ProxyHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # keep stdout clean
            pass

        # -- M1 explicitly does not tunnel. ----------------------------
        def do_CONNECT(self):
            body = b"CONNECT is M2 and is not supported in M1\n"
            self.send_response(501)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _target(self):
            """Return (host, port, endpoint) or None if unsupported."""
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

        def _handle(self):
            start = time.perf_counter()
            trace_id = self.headers.get("X-Trace-Id") or str(uuid.uuid4())
            target = self._target()
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
            length = int(self.headers.get("Content-Length") or 0)
            request_body = self.rfile.read(length) if length else b""

            headers = {}
            for key, value in self.headers.items():
                if key.lower() in HOP_BY_HOP or key.lower() == "host":
                    continue
                headers[key] = value  # forwarded, never logged
            headers["Host"] = dest_label
            headers["X-Trace-Id"] = trace_id

            task_number = state.task_number(
                trace_id, self.headers.get("X-Task-Number"))
            attempt = state.next_attempt(trace_id, endpoint, self.command)
            strategy = self.headers.get("X-Strategy") or "proxy"

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
          db_path: str = "attempts.db") -> ThreadingHTTPServer:
    state = ProxyState(db_path)
    server = ThreadingHTTPServer((host, port), make_handler(state))
    server.state = state  # type: ignore[attr-defined]
    return server


def main():
    parser = argparse.ArgumentParser(description="M1 local HTTP proxy")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8888)
    parser.add_argument("--db", default="attempts.db")
    args = parser.parse_args()
    server = serve(args.host, args.port, args.db)
    print(f"proxy listening on {args.host}:{args.port} db={args.db}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
