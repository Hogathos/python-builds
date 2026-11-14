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
import ipaddress
import json
import os
import select
import socket
import sys
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
RELAY_IDLE_TIMEOUT_SECONDS = 30.0  # tunnel silence before relay gives up

MAX_REQUEST_BODY_BYTES = 10 * 1024 * 1024  # bigger request bodies get a plain-words 413, never silent truncation
MAX_REQUEST_LINE_BYTES = 8192  # longer request lines get a plain-words 400
MAX_HEADER_BYTES = 65536  # more header bytes total get a plain-words 400
RELAY_CHUNK_BYTES = 65536  # stream step both ways: headers first, then body in chunks
MAX_BUFFERED_RESPONSE_BYTES = 1024 * 1024  # up to this many body bytes are read whole (row logged first); past it, or with no length, the body streams and its row lands when the stream ends

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-connection", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade",
}


def _parse_port(text: str, authority: str) -> int:
    """Port number or ValueError; the caller answers 400."""
    port = int(text)
    if not 0 < port < 65536:
        raise ValueError(f"bad port in {authority!r}")
    return port


def _split_authority(authority: str, default_port: int | None) -> tuple[str, int | None]:
    """Split host[:port]; bracketed [v6]:port keeps brackets off the host.

    A bare IPv6 address (more than one colon, no brackets) is the host
    with no port. Raises ValueError on a bad or missing port.
    """
    text = authority.strip()
    if text.startswith("["):
        end = text.find("]")
        if end == -1:
            raise ValueError(f"bad authority {authority!r}")
        host = text[1:end]
        rest = text[end + 1:]
        if not rest:
            return host, default_port
        if not rest.startswith(":"):
            raise ValueError(f"bad authority {authority!r}")
        return host, _parse_port(rest[1:], authority)
    if text.count(":") > 1:
        return text, default_port
    host, sep, port = text.rpartition(":")
    if not sep:
        return text, default_port
    return host, _parse_port(port, authority)


def _dotted_numbers_value(text: str) -> int | None:
    """inet_aton-style value for 1-4 numeric parts, else None.

    Parts may be decimal, 0x hex, or 0-prefixed octal, so 0x7f.0.0.1,
    0177.0.0.1, 127.1, and 2130706433 all reduce to 127.0.0.1.
    Non-numeric text returns None and is treated as a hostname.
    """
    parts = text.split(".")
    if not 1 <= len(parts) <= 4:
        return None
    nums = []
    for part in parts:
        if not part:
            return None
        try:
            if part.lower().startswith("0x"):
                nums.append(int(part, 16))
            elif len(part) > 1 and part.startswith("0") and part.isdigit():
                nums.append(int(part, 8))
            elif part.isdigit():
                nums.append(int(part, 10))
            else:
                return None
        except ValueError:
            return None
    width = {1: 32, 2: 24, 3: 16, 4: 8}[len(nums)]
    if any(n > 255 for n in nums[:-1]) or nums[-1] >= (1 << width):
        return None
    value = 0
    for num, shift in zip(nums, (24, 16, 8)[:len(nums) - 1] + (0,)):
        value |= num << shift
    return value


def _format_label(host: str, port: int | None) -> str:
    """host:port for log rows; brackets back on a bare IPv6 host."""
    if port is None:
        return host
    if ":" in host and not host.startswith("["):
        return f"[{host}]:{port}"
    return f"{host}:{port}"


def _normalize_host(text: str) -> str:
    """One canonical spelling per host, for allowlist matching only.

    Lowercase, no brackets, no trailing dot; every numeric IP form
    (hex/octal/short/decimal, IPv4-mapped IPv6) reduced to the plain
    address. Names that are not IPs compare as plain lowercase text,
    so "localhost" never equals 127.0.0.1: no DNS is consulted.
    """
    cleaned = text.strip().lower()
    if len(cleaned) > 1 and cleaned.endswith("."):
        cleaned = cleaned[:-1]
    if cleaned.startswith("[") and cleaned.endswith("]"):
        cleaned = cleaned[1:-1]
    try:
        addr = ipaddress.ip_address(cleaned)
    except ValueError:
        addr = None
    if addr is not None:
        mapped = getattr(addr, "ipv4_mapped", None)
        return str(mapped) if mapped is not None else str(addr)
    value = _dotted_numbers_value(cleaned)
    if value is not None:
        try:
            return str(ipaddress.IPv4Address(value))
        except ValueError:
            pass
    return cleaned


_NEVER_PORT = object()  # allowlist entry port that matches nothing


class _BodyTooBig(Exception):
    """Request body past MAX_REQUEST_BODY_BYTES; the caller answers 413."""


class _BadFraming(Exception):
    """Request framing the proxy refuses; the caller answers 400."""


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


def _retry_reason(attempt: int) -> str:
    """Retry marker for a log row: 'retry' unless this is attempt 1."""
    return "retry" if attempt > 1 else ""


class ProxyState:
    def __init__(self, db_path: str, retry_window: float = 10.0,
                 allowlist=None, rate_limit: int = RATE_LIMIT,
                 rate_window: float = RATE_WINDOW_SECONDS,
                 relay_timeout: float = RELAY_IDLE_TIMEOUT_SECONDS):
        self.conn = db_module.init_db(db_path)
        self.retry_window = retry_window
        self.allowlist = tuple(
            entry.strip().lower() for entry in
            (allowlist if allowlist is not None else DEFAULT_ALLOWLIST)
            if entry.strip())
        # Parsed once up front: (normalized host, port or None for any).
        # An entry that does not parse gets a port that matches nothing,
        # so a typo fails closed instead of opening the proxy.
        self._normalized_allowlist = []
        for entry in self.allowlist:
            try:
                entry_host, entry_port = _split_authority(entry, None)
                entry_host = _normalize_host(entry_host)
            except ValueError:
                entry_host, entry_port = _normalize_host(entry), _NEVER_PORT
            self._normalized_allowlist.append((entry_host, entry_port))
        self.rate_limit = int(rate_limit)
        self.rate_window = float(rate_window)
        self.relay_timeout = float(relay_timeout)
        self._lock = threading.Lock()
        self._task_by_trace: dict[str, int] = {}
        self._next_task = 1
        self._attempts: dict[tuple[str, str, str], list[float]] = {}
        self._rate_stamps: dict[str, list[float]] = {}

    def is_allowed(self, dest_host: str, dest_port: int) -> bool:
        """Allowlist entries are hosts, or host:port for one exact port.

        A bare host (IPv4, hostname, or IPv6 with or without brackets)
        matches on any port. A host:port entry matches only that exact
        port; IPv6 host:port must use brackets ([::1]:18080). Both sides
        are normalized first, so 0x7f.0.0.1, 2130706433, 0177.0.0.1,
        ::ffff:127.0.0.1, 127.1, and trailing-dot or mixed-case names
        match the same entry as their plain spelling.
        """
        host = _normalize_host(dest_host)
        for entry_host, entry_port in self._normalized_allowlist:
            if entry_host != host:
                continue
            if entry_port is None or entry_port == dest_port:
                return True
        return False

    def check_rate(self, dest_label: str) -> bool:
        """Sliding window per destination; True = this request may pass."""
        now = time.time()
        with self._lock:
            stamps = self._rate_stamps.setdefault(dest_label, [])
            stamps[:] = [s for s in stamps if now - s <= self.rate_window]
            if len(stamps) >= self.rate_limit:
                return False
            stamps.append(now)
            return True

    def task_number(self, trace_id: str, explicit: str | None) -> int:
        # One trace keeps one number: the first claim wins. An explicit
        # number taken by another trace falls back to auto-assignment,
        # and a fresh explicit number pushes the auto counter past it,
        # so explicit and auto numbers can never collide.
        with self._lock:
            if trace_id in self._task_by_trace:
                return self._task_by_trace[trace_id]
            if explicit:
                try:
                    number = int(explicit)
                except ValueError:
                    pass
                else:
                    if number not in self._task_by_trace.values():
                        self._task_by_trace[trace_id] = number
                        if number >= self._next_task:
                            self._next_task = number + 1
                        return number
            number = self._next_task
            self._next_task += 1
            self._task_by_trace[trace_id] = number
            return number

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

    def peek_attempt(self, trace_id: str, endpoint: str, method: str) -> int:
        # Would-be attempt number: counted, never consumed. Refused
        # requests log this so their rows stay numbered without shifting
        # the numbering of forwarded requests.
        now = time.time()
        key = (trace_id, endpoint, method)
        with self._lock:
            fresh = [t for t in self._attempts.get(key, [])
                     if now - t <= self.retry_window]
            return len(fresh) + 1


class _RelayTimeout(Exception):
    """Relay idle past the timeout; carries bytes relayed so far."""

    def __init__(self, bytes_in: int, bytes_out: int):
        super().__init__("relay idle past timeout")
        self.bytes_in = bytes_in
        self.bytes_out = bytes_out


class _RelayBroken(Exception):
    """A relay socket errored; carries bytes and which side broke."""

    def __init__(self, bytes_in: int, bytes_out: int, close_reason: str):
        super().__init__("relay socket broke")
        self.bytes_in = bytes_in
        self.bytes_out = bytes_out
        self.close_reason = close_reason


def _relay(client: socket.socket, upstream: socket.socket,
           timeout: float = RELAY_IDLE_TIMEOUT_SECONDS
           ) -> tuple[int, int, str]:
    """Relay raw bytes both ways; return (bytes_in, bytes_out, close_reason).

    Bytes are counted, never inspected, stored, or logged. bytes_in is
    client -> destination, bytes_out is destination -> client. Silence
    longer than timeout raises _RelayTimeout with partial counts; a
    socket error raises _RelayBroken naming the side that broke.
    """
    bytes_in = bytes_out = 0
    sockets = [client, upstream]
    while True:
        readable, _, _ = select.select(sockets, [], [], timeout)
        if not readable:
            raise _RelayTimeout(bytes_in, bytes_out)
        for sock in readable:
            try:
                data = sock.recv(65536)
            except OSError:
                raise _RelayBroken(
                    bytes_in, bytes_out,
                    "client_eof" if sock is client else "upstream_reset")
            if not data:
                return bytes_in, bytes_out, "success"
            try:
                if sock is client:
                    upstream.sendall(data)
                    bytes_in += len(data)
                else:
                    client.sendall(data)
                    bytes_out += len(data)
            except OSError:
                raise _RelayBroken(
                    bytes_in, bytes_out,
                    "upstream_reset" if sock is client else "client_eof")


def make_handler(state: ProxyState):
    class ProxyHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # keep stdout clean
            pass

        # -- M2: CONNECT tunnelling, bytes only, never decrypted. -----
        def do_CONNECT(self):
            start = time.perf_counter()
            trace_id = self.headers.get("X-Trace-Id") or str(uuid.uuid4())
            try:
                dest_host, dest_port = _split_authority(self.path, 443)
            except ValueError:
                # Unparseable authority: keep the old shape (blocked row,
                # 403) rather than inventing a new refusal for it.
                dest_host, dest_port = self.path, -1
            endpoint = _format_label(dest_host, dest_port)
            task_number = state.task_number(
                trace_id, self.headers.get("X-Task-Number"))
            strategy = self.headers.get("X-Strategy") or "proxy"

            def log_connect(status, outcome, reason, http_status,
                            bytes_in, bytes_out, close_reason,
                            connect_ms=None):
                duration_ms = (time.perf_counter() - start) * 1000.0
                db_module.log_attempt(
                    state.conn, trace_id=trace_id,
                    task_number=task_number, attempt=attempt,
                    strategy=strategy, status=status,
                    latency_seconds=duration_ms / 1000.0,
                    retry_reason=_retry_reason(attempt),
                    dest_host=endpoint, endpoint=endpoint,
                    method="CONNECT", bytes_in=bytes_in,
                    bytes_out=bytes_out, http_status=http_status,
                    outcome=outcome, reason=reason,
                    bytes_tx=bytes_in, bytes_rx=bytes_out,
                    close_reason=close_reason, connect_ms=connect_ms,
                    duration_ms=duration_ms)

            if not state.is_allowed(dest_host, dest_port):
                attempt = state.peek_attempt(trace_id, endpoint, "CONNECT")
                log_connect("blocked", "blocked", "not_allowlisted", 403,
                            0, 0, "blocked_allowlist")
                self.send_response(403)
                self.send_header("X-Trace-Id", trace_id)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if not state.check_rate(endpoint):
                attempt = state.peek_attempt(trace_id, endpoint, "CONNECT")
                log_connect("rate_limited", "rate_limited", "rate_limited",
                            429, 0, 0, "rate_limited")
                self.send_response(429)
                self.send_header("X-Trace-Id", trace_id)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            # Numbered only once the tunnel will actually be opened.
            attempt = state.next_attempt(trace_id, endpoint, "CONNECT")
            upstream = None
            connect_start = time.perf_counter()
            try:
                upstream = socket.create_connection(
                    (dest_host, dest_port), timeout=10)
                connect_ms = (time.perf_counter() - connect_start) * 1000.0
            except Exception:
                connect_ms = (time.perf_counter() - connect_start) * 1000.0
                log_connect("failure", "allowed", "", None, 0, 0,
                            "upstream_reset", connect_ms)
                self.send_response(502)
                self.send_header("X-Trace-Id", trace_id)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            self.send_response(200)
            self.send_header("X-Trace-Id", trace_id)
            self.end_headers()
            self.wfile.flush()
            self.close_connection = True
            status, bytes_in, bytes_out, close_reason = "success", 0, 0, "success"
            try:
                bytes_in, bytes_out, close_reason = _relay(
                    self.connection, upstream, timeout=state.relay_timeout)
            except _RelayTimeout as exc:
                # A silent tunnel tells us nothing about who is at fault,
                # so the status stays unknown, never failed.
                status = "unknown"
                bytes_in, bytes_out = exc.bytes_in, exc.bytes_out
                close_reason = "relay_timeout"
            except _RelayBroken as exc:
                status = "failure"
                bytes_in, bytes_out = exc.bytes_in, exc.bytes_out
                close_reason = exc.close_reason
            except Exception:
                status = "failure"
                close_reason = "unknown"
            finally:
                upstream.close()
            log_connect(status, "allowed", "", None, bytes_in, bytes_out,
                        close_reason, connect_ms)

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
                try:
                    port = parsed.port or 80
                except ValueError:
                    raise ValueError(f"bad port in {self.path!r}")
                return parsed.hostname, port, endpoint
            host_header = self.headers.get("Host", "")
            if not host_header:
                return None
            host, port = _split_authority(host_header, 80)
            if not host:
                raise ValueError(f"bad host in {host_header!r}")
            return host, port, self.path

        def send_error(self, code, message=None, explain=None):
            # Unknown methods land here (no do_<METHOD> exists). Log a row
            # with plain words instead of the stdlib silent HTML 501.
            if code == http.client.NOT_IMPLEMENTED and hasattr(self, "command"):
                if not hasattr(self, "_refused_start"):
                    self._refused_start = time.perf_counter()
                headers = getattr(self, "headers", None) or {}
                get = headers.get if hasattr(headers, "get") else (lambda k, d=None: d)
                trace_id = get("X-Trace-Id") or str(uuid.uuid4())
                body = (f"{self.command} is not supported by this proxy, "
                        "request not forwarded by proxy\n").encode()
                self._refused(501, "failure", "unimplemented_method",
                              get("Host") or "", self.path or "", body,
                              trace_id=trace_id)
                return
            super().send_error(code, message, explain)

        def _refused(self, code, status, reason, dest_host, endpoint,
                     body, trace_id=None, close_reason="unknown"):
            """Refuse a request with a plain-words body plus an audit row."""
            if trace_id is None:
                trace_id = self.headers.get("X-Trace-Id") or str(uuid.uuid4())
            task_number = state.task_number(
                trace_id, self.headers.get("X-Task-Number"))
            attempt = state.peek_attempt(trace_id, endpoint, self.command
                                         if hasattr(self, "command") else "")
            strategy = self.headers.get("X-Strategy") or "proxy"
            duration_ms = None
            start = getattr(self, "_refused_start", None)
            if start is not None:
                duration_ms = (time.perf_counter() - start) * 1000.0
            db_module.log_attempt(
                state.conn, trace_id=trace_id,
                task_number=task_number, attempt=attempt,
                strategy=strategy, status=status,
                latency_seconds=(duration_ms / 1000.0
                                 if duration_ms is not None else 0.0),
                retry_reason=_retry_reason(attempt),
                dest_host=dest_host, endpoint=endpoint,
                method=getattr(self, "command", ""),
                bytes_in=0, bytes_out=0,
                http_status=code, outcome=status, reason=reason,
                close_reason=close_reason, duration_ms=duration_ms)
            self.send_response(code)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Trace-Id", trace_id)
            self.end_headers()
            try:
                self.wfile.write(body)
            except OSError:
                pass
            self.close_connection = True

        def _chunked_body(self):
            """Yield de-chunked request body pieces from a chunked request.

            Raises _BadFraming on bad chunk framing, _BodyTooBig past the cap.
            """
            total = 0
            while True:
                line = self.rfile.readline(MAX_REQUEST_LINE_BYTES + 1)
                if not line.endswith(b"\n") or len(line) > MAX_REQUEST_LINE_BYTES:
                    raise _BadFraming("chunk size line too long")
                try:
                    size = int(line.split(b";")[0].strip(), 16)
                except ValueError:
                    raise _BadFraming("bad chunk size")
                if size < 0:
                    raise _BadFraming("negative chunk size")
                if size == 0:
                    while True:  # trailers are read and ignored, never logged
                        trailer = self.rfile.readline(
                            MAX_REQUEST_LINE_BYTES + 1)
                        if trailer in (b"\r\n", b"\n", b""):
                            return
                        if (not trailer.endswith(b"\n")
                                or len(trailer) > MAX_REQUEST_LINE_BYTES):
                            raise _BadFraming("trailer line too long")
                total += size
                if total > MAX_REQUEST_BODY_BYTES:
                    raise _BodyTooBig()
                piece = b""
                while len(piece) < size:
                    block = self.rfile.read(size - len(piece))
                    if not block:
                        raise _BadFraming("request body ended early")
                    piece += block
                crlf = self.rfile.read(2)
                if crlf != b"\r\n":
                    raise _BadFraming("chunk missing CRLF")
                yield piece

        def _forward_body(self, upstream, chunked, length):
            """Stream the client body upstream; return bytes sent that way."""
            if chunked:
                sent = 0
                for piece in self._chunked_body():
                    upstream.send(b"%X\r\n" % len(piece))
                    upstream.send(piece)
                    upstream.send(b"\r\n")
                    sent += len(piece)
                upstream.send(b"0\r\n\r\n")
                return sent
            sent = 0
            while sent < length:
                piece = self.rfile.read(min(RELAY_CHUNK_BYTES, length - sent))
                if not piece:
                    raise _BadFraming("request body ended early")
                upstream.send(piece)
                sent += len(piece)
            return sent

        def _reject_malformed_header(self, state, trace_id, start):
            """400 plus an audit row for an unparseable destination."""
            task_number = state.task_number(
                trace_id, self.headers.get("X-Task-Number"))
            attempt = state.peek_attempt(trace_id, self.path, self.command)
            strategy = self.headers.get("X-Strategy") or "proxy"
            body = b"failure: request not forwarded by proxy\n"
            db_module.log_attempt(
                state.conn, trace_id=trace_id,
                task_number=task_number, attempt=attempt,
                strategy=strategy, status="failure",
                latency_seconds=time.perf_counter() - start,
                retry_reason=_retry_reason(attempt),
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
            self._refused_start = start
            trace_id = self.headers.get("X-Trace-Id") or str(uuid.uuid4())
            if len(self.requestline) > MAX_REQUEST_LINE_BYTES:
                self._refused(400, "failure", "malformed_header", "",
                              self.path,
                              b"request line too long, request not forwarded by proxy\n",
                              trace_id=trace_id)
                return
            if sum(len(k) + len(v)
                   for k, v in self.headers.items()) > MAX_HEADER_BYTES:
                self._refused(400, "failure", "malformed_header", "",
                              self.path,
                              b"headers too big, request not forwarded by proxy\n",
                              trace_id=trace_id)
                return
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
            # The blocked row shows this exact host:port, so the dashboard
            # can name what the allowlist stopped.
            dest_label = _format_label(dest_host, dest_port)
            task_number = state.task_number(
                trace_id, self.headers.get("X-Task-Number"))
            strategy = self.headers.get("X-Strategy") or "proxy"

            def reject(code, status, reason, close_reason="unknown"):
                body = f"{status}: request not forwarded by proxy\n".encode()
                self._refused(code, status, reason, dest_label, endpoint,
                              body, trace_id=trace_id,
                              close_reason=close_reason)

            if "upgrade" in self.headers:
                self._refused(
                    501, "failure", "upgrade_needs_connect",
                    dest_label, endpoint,
                    b"WebSocket needs CONNECT: send a CONNECT tunnel, "
                    b"not Upgrade on plain HTTP\n",
                    trace_id=trace_id)
                return
            if not state.is_allowed(dest_host, dest_port):
                reject(403, "blocked", "not_allowlisted",
                       close_reason="blocked_allowlist")
                return
            if not state.check_rate(dest_label):
                reject(429, "rate_limited", "rate_limited",
                       close_reason="rate_limited")
                return

            # Request smuggling hygiene: one length, one framing, never both.
            lengths = [v.strip() for v in
                       (self.headers.get_all("Content-Length") or [])]
            # Any repeat is refused, even two identical ones: dedupe
            # here and a smuggled length slips past the single read below.
            if len(lengths) > 1:
                reject(400, "failure", "duplicate_content_length")
                return
            coding = [t.strip() for t in
                      self.headers.get("Transfer-Encoding", "").lower().split(",")
                      if t.strip()]
            chunked = "chunked" in coding
            if lengths and chunked:
                reject(400, "failure",
                       "content_length_with_transfer_encoding")
                return
            if coding and not chunked:
                reject(501, "failure", "unsupported_transfer_coding")
                return
            try:
                length = int(lengths[0]) if lengths else 0
                if length < 0:
                    raise ValueError("negative Content-Length")
            except ValueError:
                reject(400, "failure", "malformed_header")
                return
            if length > MAX_REQUEST_BODY_BYTES:
                self._refused(
                    413, "failure", "body_too_big", dest_label, endpoint,
                    f"request body too big: {length} bytes, "
                    f"limit {MAX_REQUEST_BODY_BYTES}, "
                    "request not forwarded by proxy\n".encode(),
                    trace_id=trace_id)
                return
            # Numbered only once the request will actually be forwarded.
            attempt = state.next_attempt(trace_id, endpoint, self.command)

            headers = {}
            for key, value in self.headers.items():
                lowered = key.lower()
                if lowered in HOP_BY_HOP or lowered == "host":
                    continue
                if lowered == "content-length" and chunked:
                    continue  # re-framed as chunked below
                if lowered in ("x-task-number", "x-strategy"):
                    continue  # proxy control headers: used locally, never forwarded
                headers[key] = value  # forwarded, never logged
            headers["Host"] = dest_label
            headers["X-Trace-Id"] = trace_id
            if chunked:
                headers["Transfer-Encoding"] = "chunked"

            status, http_status = "error", 502
            bytes_tx = bytes_rx = 0
            close_reason = "upstream_reset"
            connect_ms = None
            resp_headers: dict = {}
            try:
                # One-shot upstream: a fresh connection per request, no pool — threads share nothing.
                upstream = http.client.HTTPConnection(
                    dest_host, dest_port, timeout=10)
                connect_start = time.perf_counter()
                try:
                    upstream.connect()
                finally:
                    connect_ms = ((time.perf_counter() - connect_start)
                                  * 1000.0)
                upstream.putrequest(self.command, endpoint, skip_host=1)
                for key, value in headers.items():
                    upstream.putheader(key, value)
                upstream.endheaders()
                bytes_tx = self._forward_body(upstream, chunked, length)
                resp = upstream.getresponse()
                http_status = resp.status
                status = ("success" if 200 <= http_status < 400 else "failure")
                close_reason = "success"
                resp_headers = dict(resp.getheaders())
            except (_BadFraming, _BodyTooBig) as framing_error:
                upstream.close()
                over_cap = isinstance(framing_error, _BodyTooBig)
                code = 413 if over_cap else 400
                reason = "body_too_big" if over_cap else "malformed_header"
                body = (f"request body past the {MAX_REQUEST_BODY_BYTES} "
                        "byte cap, request not forwarded by proxy\n".encode()
                        if over_cap else
                        b"request body ended early, request not forwarded by proxy\n")
                db_module.log_attempt(
                    state.conn, trace_id=trace_id, task_number=task_number,
                    attempt=attempt, strategy=strategy, status="failure",
                    latency_seconds=time.perf_counter() - start,
                    retry_reason=_retry_reason(attempt),
                    dest_host=dest_label, endpoint=endpoint,
                    method=self.command, http_status=code,
                    outcome="failure", reason=reason,
                    close_reason="unknown",
                    connect_ms=connect_ms,
                    duration_ms=(time.perf_counter() - start) * 1000.0)
                self.send_response(code)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("X-Trace-Id", trace_id)
                self.end_headers()
                self.wfile.write(body)
                self.close_connection = True
                return
            except Exception:
                # Logged before the client is answered: everything about
                # this row is already known, so no reader has to wait.
                duration_ms = (time.perf_counter() - start) * 1000.0
                db_module.log_attempt(
                    state.conn, trace_id=trace_id, task_number=task_number,
                    attempt=attempt, strategy=strategy, status="error",
                    latency_seconds=duration_ms / 1000.0,
                    retry_reason=_retry_reason(attempt),
                    dest_host=dest_label, endpoint=endpoint,
                    method=self.command, bytes_in=bytes_tx, bytes_out=0,
                    http_status=502, outcome="allowed", reason="",
                    bytes_tx=bytes_tx, bytes_rx=0,
                    close_reason="upstream_reset", connect_ms=connect_ms,
                    duration_ms=duration_ms)
                response_body = b"Bad Gateway\n"
                self.send_response(502)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(response_body)))
                self.send_header("X-Trace-Id", trace_id)
                self.end_headers()
                self.wfile.write(response_body)
                self.close_connection = True
                return

            upstream_length = resp_headers.get("Content-Length")
            try:
                upstream_length = (int(upstream_length)
                                   if upstream_length is not None else None)
            except ValueError:
                upstream_length = None
            # Small bodies stay buffered: the row (usage included) is
            # logged before the client sees the response, as before. Big
            # or length-unknown bodies stream in chunks instead, and their
            # row lands once the stream ends — readers must allow for that.
            buffered = (upstream_length is not None
                        and upstream_length <= MAX_BUFFERED_RESPONSE_BYTES)
            if buffered:
                response_body = resp.read()
                upstream.close()
                bytes_rx = len(response_body)
                duration_ms = (time.perf_counter() - start) * 1000.0
                input_tokens = _usage_input_tokens(
                    response_body, resp_headers.get("Content-Type", ""))
                db_module.log_attempt(
                    state.conn, trace_id=trace_id, task_number=task_number,
                    attempt=attempt, strategy=strategy, status=status,
                    latency_seconds=duration_ms / 1000.0,
                    input_tokens=input_tokens, cost_dollars=0.0,
                    retry_reason=_retry_reason(attempt),
                    dest_host=dest_label, endpoint=endpoint,
                    method=self.command, bytes_in=bytes_tx,
                    bytes_out=bytes_rx, http_status=http_status,
                    outcome="allowed", reason="",
                    bytes_tx=bytes_tx, bytes_rx=bytes_rx,
                    close_reason=close_reason, connect_ms=connect_ms,
                    duration_ms=duration_ms)
                self.send_response(http_status)
                for key, value in resp_headers.items():
                    if (key.lower() in HOP_BY_HOP
                            or key.lower() == "content-length"):
                        continue
                    self.send_header(key, value)
                self.send_header("Content-Length", str(bytes_rx))
                self.send_header("X-Trace-Id", trace_id)
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(response_body)
                return

            # Headers first, then the body in chunks, so streams and big
            # downloads start arriving instead of buffering whole.
            self.send_response(http_status)
            for key, value in resp_headers.items():
                if key.lower() in HOP_BY_HOP or key.lower() == "content-length":
                    continue
                self.send_header(key, value)
            if upstream_length is not None:
                self.send_header("Content-Length", str(upstream_length))
            else:
                self.close_connection = True  # close-delimited: no length known
            self.send_header("X-Trace-Id", trace_id)
            self.end_headers()
            if self.command != "HEAD":
                try:
                    while True:
                        # Framed bodies (length or chunked) arrive piece by
                        # piece through read. A close-delimited body has no
                        # frame, so read would wait for EOF instead of
                        # returning what is here; read1 takes what is
                        # buffered and arrived, including bytes the header
                        # read already pulled into the response buffer.
                        # Idle over 10 s on the upstream socket ends the
                        # stream (caught below as upstream_reset).
                        if resp.chunked or upstream_length is not None:
                            piece = resp.read(RELAY_CHUNK_BYTES)
                        else:
                            piece = resp.fp.read1(RELAY_CHUNK_BYTES)
                        if not piece:
                            break
                        bytes_rx += len(piece)
                        self.wfile.write(piece)
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    close_reason = "client_eof"
                    status = "failure"
                except Exception:
                    close_reason = "upstream_reset"
                    status = "failure"
            upstream.close()

            duration_ms = (time.perf_counter() - start) * 1000.0
            input_tokens = 0  # streamed bodies are never re-read for usage
            db_module.log_attempt(
                state.conn,
                trace_id=trace_id,
                task_number=task_number,
                attempt=attempt,
                strategy=strategy,
                status=status,
                latency_seconds=duration_ms / 1000.0,
                input_tokens=input_tokens,
                cost_dollars=0.0,
                retry_reason=_retry_reason(attempt),
                dest_host=dest_label,
                endpoint=endpoint,
                method=self.command,
                bytes_in=bytes_tx,
                bytes_out=bytes_rx,
                http_status=http_status,
                outcome="allowed",
                reason="",
                bytes_tx=bytes_tx,
                bytes_rx=bytes_rx,
                close_reason=close_reason,
                connect_ms=connect_ms,
                duration_ms=duration_ms,
            )

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
          rate_window: float = RATE_WINDOW_SECONDS,
          relay_timeout: float = RELAY_IDLE_TIMEOUT_SECONDS
          ) -> ThreadingHTTPServer:
    state = ProxyState(db_path, allowlist=allowlist,
                       rate_limit=rate_limit, rate_window=rate_window,
                       relay_timeout=relay_timeout)
    server = ThreadingHTTPServer((host, port), make_handler(state))
    server.state = state  # type: ignore[attr-defined]
    return server


def _is_windows_drive_path(path: str) -> bool:
    """True for paths like C:/x or C:\\x, on any platform."""
    return len(path) >= 3 and path[1] == ":" and path[0].isalpha() and path[2] in ("/", "\\")


def _default_db_path() -> str:
    """Project-folder attempts.db, wherever the process was started from.

    Frozen exe inside dist/ -> the project folder above dist/.
    Frozen exe elsewhere -> beside the exe. Plain python -> beside proxy.py.
    Windows drive paths (C:/...) count as absolute on every platform,
    so POSIX CI never prefixes them with its working directory.
    """
    if getattr(sys, "frozen", False):
        exe = sys.executable
        if _is_windows_drive_path(exe):
            from pathlib import PureWindowsPath
            exe_path = PureWindowsPath(exe)
            exe_dir = exe_path.parent
            if exe_dir.name.lower() == "dist":
                candidate = exe_dir.parent / "attempts.db"
            else:
                candidate = exe_dir / "attempts.db"
            if os.name == "nt":
                return str(candidate)
            return candidate.as_posix()
        exe_dir = os.path.dirname(os.path.abspath(exe))
        if os.path.basename(exe_dir).lower() == "dist":
            return os.path.join(os.path.dirname(exe_dir), "attempts.db")
        return os.path.join(exe_dir, "attempts.db")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "attempts.db")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="M1-M4 local proxy (HTTP + CONNECT + allowlist/rate limit)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8888)
    parser.add_argument("--db", default=_default_db_path())
    parser.add_argument("--allowlist", default=",".join(DEFAULT_ALLOWLIST),
                        help="comma-separated allowed hosts (or host:port)")
    parser.add_argument("--rate-limit", type=int, default=RATE_LIMIT)
    parser.add_argument("--rate-window", type=float,
                        default=RATE_WINDOW_SECONDS)
    parser.add_argument("--relay-timeout", type=float,
                        default=RELAY_IDLE_TIMEOUT_SECONDS,
                        help="seconds of CONNECT tunnel silence before "
                             "the relay gives up (default 30)")
    return parser


def main():
    args = build_parser().parse_args()
    server = serve(args.host, args.port, args.db,
                   allowlist=args.allowlist.split(","),
                   rate_limit=args.rate_limit, rate_window=args.rate_window,
                   relay_timeout=args.relay_timeout)
    print(f"proxy listening on {args.host}:{args.port} db={args.db}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
