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

Steer Pause one Run: a human pauses one Run by trace_id. The pause is
journaled first (outcome paused, verdict unknown), then that Run's live
tunnel is cut and its later traffic is refused. Other Runs are not
touched. A retry without a fresh Verify is blocked and journaled;
after a fresh Verify the retry is allowed and journaled. Pause rows
are metadata only and always cost $0.00.

Steer Redirect one Run: a human moves one Run to a new allowlisted
loopback destination by trace_id. The redirect is journaled first
(outcome redirected, verdict unknown), then the Run's live tunnel is
cut and later traffic for that trace_id goes to the new destination.
Other Runs keep their routes. A redirect to a non-allowlisted name is
refused and journaled, and the Run stays where it was: never back to
the old destination, never forward to the refused one. A retry on the
new destination without a fresh Verify is blocked and journaled; after
a fresh Verify it is allowed and journaled. Redirect rows are metadata
only and always cost $0.00.

Steer Red button: a human stops all Runs at once. Every known Run gets
a stop row first (outcome stopped, verdict unknown), then every live
tunnel is cut. No Run keeps working, paused or flowing. After the
button, any traffic without a fresh human approval plus Verify is
refused and journaled: no fail-open to new Runs, and old Runs never
restart on their own. A fresh approval plus Verify lets a new Run
through; old Runs stay stopped. The journal is only added to, never
deleted. Stop rows are metadata only and always cost $0.00.
"""
from __future__ import annotations

import argparse
import datetime
import http.client
import ipaddress
import json
import os
import select
import socket
import sqlite3
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
        # Steer Pause one Run: paused Runs by trace_id (survive restart,
        # never auto-resume), fresh Verify stamps, live tunnel sockets.
        self._paused: dict[str, dict] = db_module.load_paused(self.conn)
        self._verified: dict[str, str] = {}
        self._live: dict[str, set] = {}
        # Steer Redirect one Run: human-chosen destination per trace_id
        # (survives restart, never silently undone).
        self._redirects: dict[str, dict] = db_module.load_redirected(
            self.conn)
        # Steer Red button: global stop (survives restart, never
        # auto-lifted), the stopped trace set (old Runs never restart
        # alone), plus fresh human approvals for new Runs.
        self._stopped: dict | None = db_module.load_red_button(self.conn)
        self._stopped_traces: set = db_module.load_red_button_traces(
            self.conn)
        self._approved: dict[str, str] = {}
        # Steer per-network override: rule per destination, human-only,
        # journal first, fail-closed. Survives restart, never silently
        # lifted, same as every other Steer control.
        self._overrides: dict[str, dict] = db_module.load_overrides(
            self.conn)
        # Steer spend caps: per-network dollar caps, human-only, journal
        # first. Survives restart, never silently lifted. Warned flags
        # and pause-by-cap traces live here; the rules live in SQLite.
        self._caps: dict[str, dict] = db_module.load_caps(self.conn)
        self._cap_warned: set = set()
        self._cap_paused: dict[str, str] = {}
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

    # -- Steer Pause one Run. Human-only: these are plain methods on the
    # local proxy state, never an HTTP route, so proxied agent traffic
    # cannot call them. Local-first, fail-closed: if Iris dies, the
    # proxy is down and the agent stops, not continues. -------------

    def is_paused(self, trace_id: str) -> bool:
        """True when this Run is paused: nothing forwards for it."""
        with self._lock:
            return trace_id in self._paused

    def pause_reason(self, trace_id: str) -> str:
        """Why this Run is paused, or "paused" when it is not."""
        with self._lock:
            entry = self._paused.get(trace_id)
            return entry["reason"] if entry else "paused"

    def redirect_target(self, trace_id: str) -> str | None:
        """Human-chosen destination label for this Run, or None."""
        with self._lock:
            entry = self._redirects.get(trace_id)
            return entry["dest_host"] if entry else None

    def steer_cut(self, trace_id: str):
        """(outcome, reason) when this Run was steered mid-flight.

        Returns None when the Run was not paused, redirected, or
        Red-button stopped, so a normal tunnel close keeps its own
        status and outcome.
        """
        with self._lock:
            if trace_id in self._paused:
                return ("paused", self._paused[trace_id]["reason"])
            if trace_id in self._redirects:
                return ("redirected", self._redirects[trace_id]["reason"])
            if self._stopped is not None:
                return ("stopped", self._stopped["reason"])
            return None

    def redirect_run(self, trace_id: str, new_dest: str,
                     reason: str = "human redirect") -> bool:
        """Move one Run to a new allowlisted destination. Journal first.

        Human-only: a plain method on the local proxy state, never an
        HTTP route, so proxied agent traffic cannot call it. The new
        destination must be allowlisted loopback: anything else is
        refused and journaled (outcome blocked, reason "redirect refused:
        not allowlisted"), and the Run stays exactly where it was.
        On success the state save plus journal commit (outcome
        redirected, status unknown: Unverified explicitly) happen first,
        then the Run's live tunnel is cut and later traffic for this
        trace_id goes to the new destination. Other Runs keep their
        routes. A new redirect needs a fresh Verify before any retry.
        """
        if reason not in ("human redirect", "Steer redirect"):
            return False
        try:
            new_host, new_port = _split_authority(new_dest, 443)
            new_label = _format_label(new_host, new_port)
        except ValueError:
            new_host, new_port, new_label = None, None, ""
        if not new_label or not self.is_allowed(new_host, new_port):
            last = db_module.last_attempt(self.conn, trace_id)
            dest_host = last["dest_host"] if last else ""
            endpoint = last["endpoint"] if last else ""
            method = last["method"] if last else ""
            self._control_row(trace_id, method, dest_host, endpoint,
                              "unknown", "blocked",
                              "redirect refused: not allowlisted",
                              "redirected")
            return False
        last = db_module.last_attempt(self.conn, trace_id)
        method = last["method"] if last else ""
        endpoint = last["endpoint"] if last else ""
        now = datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds")
        db_module.save_redirected(self.conn, trace_id, new_label,
                                  reason, now)
        self._control_row(trace_id, method, new_label, new_label,
                          "unknown", "redirected", reason, "redirected")
        with self._lock:
            self._redirects[trace_id] = {"dest_host": new_label,
                                         "reason": reason,
                                         "created_at": now}
            self._verified.pop(trace_id, None)
            live = self._live.pop(trace_id, set())
        for sock in live:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        return True

    def cap_rule(self, dest_label: str):
        """Spend-cap rule for one network, or None when there is none.

        Rules are keyed by the full destination, host plus port: a cap
        on 127.0.0.1:9001 never touches 127.0.0.1:9002.
        """
        with self._lock:
            return self._caps.get(dest_label)

    def capped_total(self, dest_label: str) -> float:
        """Recorded priced spend for one network. Unverified excluded.

        Sums attempt_cost over allowed rows only: control rows cost
        nothing, and rows with no priced cost (Unverified, never
        guessed) contribute nothing. Rounded to cents: this is money.
        """
        from api import attempt_cost
        total = 0.0
        for outcome, dest_host, cost in self.conn.execute(
                "SELECT outcome, dest_host, cost_dollars FROM attempts"
                " WHERE dest_host = ? AND outcome = 'allowed'",
                (dest_label,)):
            priced = attempt_cost({"outcome": outcome,
                                   "dest_host": dest_host,
                                   "cost_dollars": cost,
                                   "status": "success"})
            if priced is not None:
                total += priced
        return round(total, 2)

    def set_cap(self, dest_label: str, cap, reason: str = "human cap") -> bool:
        """Set a spend cap in dollars for one network. Journal first.

        Human-only: a plain method on the local proxy state, never an
        HTTP route, so proxied agent traffic cannot set one. The
        destination must parse and be allowlisted, and the cap must be
        a positive number; anything else is refused with no row. On
        success the rule save plus journal row commit first (outcome
        empty, reason "cap set $X.XX"). Later traffic for the network
        warns at 80% and blocks at 100%, both journaled.
        """
        if reason not in ("human cap", "Steer cap"):
            return False
        try:
            host, port = _split_authority(dest_label, 443)
            label = _format_label(host, port)
        except ValueError:
            return False
        try:
            amount = float(cap)
        except (TypeError, ValueError):
            return False
        if not amount > 0 or not self.is_allowed(host, port):
            return False
        now = datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds")
        db_module.save_cap(self.conn, label, amount, reason, now)
        with self._lock:
            self._caps[label] = {"cap": amount, "reason": reason,
                                 "created_at": now}
            self._cap_warned.discard(label)
        self._control_row("", "CAP", label, label,
                          "unknown", "", f"cap set ${amount:.2f}", "capped")
        return True

    def unblock_cap(self, dest_label: str,
                    reason: str = "human unblock") -> bool:
        """Lift a spend cap after Verify. Human-only, journaled.

        Human-only: a plain method on the local proxy state, never an
        HTTP route. Refuses (False, no row) when there is no cap or the
        reason is not human. Otherwise journals the lift, forgets the
        rule, and unpauses the Runs the cap had stopped. Later Runs
        start clean; old pause rows stay in the journal.
        """
        if reason not in ("human unblock", "Steer unblock"):
            return False
        with self._lock:
            if dest_label not in self._caps:
                return False
        now = datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds")
        db_module.clear_cap(self.conn, dest_label)
        with self._lock:
            self._caps.pop(dest_label, None)
            self._cap_warned.discard(dest_label)
        self._control_row("", "CAP", dest_label, dest_label,
                          "unknown", "", "cap lifted", "capped")
        with self._lock:
            stopped = [tid for tid, dest in self._cap_paused.items()
                       if dest == dest_label]
        for trace_id in stopped:
            db_module.clear_paused(self.conn, trace_id)
            with self._lock:
                self._paused.pop(trace_id, None)
                self._verified.pop(trace_id, None)
                self._cap_paused.pop(trace_id, None)
        return True

    def _cap_block(self, dest_label: str) -> None:
        """Journal-then-cut for a network at its cap. Human set it up;
        this is the enforcement half, and it journals every step.

        Every live tunnel on the network gets a pause row first, then
        the sockets shut. Retries stay blocked until a fresh Verify,
        through the existing gate.
        """
        now = datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            live = {tid: dict(socks) for tid, socks in self._live.items()
                    if any(d == dest_label for d in socks.values())}
        for trace_id in live:
            last = db_module.last_attempt(self.conn, trace_id)
            method = last["method"] if last else ""
            db_module.save_paused(self.conn, trace_id,
                                  "cap block 100%", now)
            self._control_row(trace_id, method, dest_label, dest_label,
                              "unknown", "paused", "cap block 100%",
                              "capped")
            with self._lock:
                self._paused[trace_id] = {"reason": "cap block 100%",
                                          "created_at": now}
                self._verified.pop(trace_id, None)
                self._cap_paused[trace_id] = dest_label
        with self._lock:
            socks = [sock for tid in live
                     for sock in self._live.pop(tid, {}).keys()]
        for sock in socks:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def override_rule(self, dest_label: str):
        """Override rule for one destination, or None when there is none.

        Rules are keyed by the full destination, host plus port: a rule
        for 127.0.0.1:9001 never touches 127.0.0.1:9002.
        """
        with self._lock:
            return self._overrides.get(dest_label)

    def set_override(self, dest_label: str, action: str = "pause",
                     reason: str = "human override", target: str = "") -> bool:
        """Set a human override for one network. Journal first.

        Human-only: a plain method on the local proxy state, never an
        HTTP route, so proxied agent traffic cannot call it. Only the
        pause action is built; allow, block, and redirect are named for
        later tests and refused here. The destination must parse and be
        allowlisted: anything else is refused and journaled (outcome
        blocked, reason "non-allowlisted override name", dest = the name
        as given), and nothing is cut. On success the rule save plus the
        pause journal rows commit first, then every live tunnel on that
        network is cut, and later traffic for it is refused. Other
        networks keep flowing. Retries need a fresh Verify, through the
        existing gate.
        """
        if reason not in ("human override", "Steer override"):
            return False
        if action != "pause":
            return False
        try:
            host, port = _split_authority(dest_label, 443)
            label = _format_label(host, port)
        except ValueError:
            host, port, label = None, None, ""
        if not label or not self.is_allowed(host, port):
            # The refusal names a destination, not a Run: no Run existed,
            # none is invented. It journals under its own override-attempt
            # trace so the audit trail has exactly one row for it and no
            # Run's history is touched.
            attempt_trace = f"override::{dest_label}"
            self._control_row(attempt_trace, "", dest_label, dest_label,
                              "unknown", "blocked",
                              "non-allowlisted override name",
                              "overridden")
            return False
        now = datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds")
        db_module.save_override(self.conn, label, action, target,
                                reason, now)
        with self._lock:
            self._overrides[label] = {"action": action, "target": target,
                                      "reason": reason, "created_at": now}
            live_traces = [tid for tid, socks in self._live.items()
                           if any(d == label for d in socks.values())]
        for trace_id in live_traces:
            last = db_module.last_attempt(self.conn, trace_id)
            method = last["method"] if last else ""
            db_module.save_paused(self.conn, trace_id, reason, now)
            self._control_row(trace_id, method, label, label,
                              "unknown", "paused", reason, "paused")
            with self._lock:
                self._paused[trace_id] = {"reason": reason,
                                          "created_at": now}
                self._verified.pop(trace_id, None)
        with self._lock:
            live = [sock for tid in live_traces
                    for sock in self._live.pop(tid, {}).keys()]
        for sock in live:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        return True

    def _control_row(self, trace_id: str, method: str, dest_host: str,
                     endpoint: str, status: str, outcome: str,
                     reason: str, close_reason: str,
                     cost_dollars: float = 0.0) -> None:
        """One journal row for a Steer control action. Metadata only.

        No bodies, no keys, no hostnames beyond the loopback destination
        label already on the Run's own rows. Cost is $0.00, except a
        spend-cap warn row, which carries the cumulative total that
        tripped it: saying what was spent is the warning.
        """
        now = datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds")
        task_number = self.task_number(trace_id, None)
        attempt = self.peek_attempt(trace_id, endpoint, method)
        db_module.log_attempt(
            self.conn, trace_id=trace_id,
            task_number=task_number, attempt=attempt,
            strategy="proxy", status=status,
            latency_seconds=0.0,
            retry_reason=_retry_reason(attempt),
            dest_host=dest_host, endpoint=endpoint,
            method=method, bytes_in=0, bytes_out=0,
            http_status=None, created_at=now,
            outcome=outcome, reason=reason,
            cost_dollars=cost_dollars,
            close_reason=close_reason)

    def pause_run(self, trace_id: str,
                  reason: str = "human pause") -> bool:
        """Pause one Run by trace_id. Journal first, then cut.

        Writes the paused state and the pause row (outcome paused,
        status unknown: Unverified, explicitly, never Correct and never
        Incorrect from a pause alone), and only then shuts the Run's
        live tunnel sockets. Other Runs keep their tunnels. A new pause
        needs a fresh Verify before any retry. Idempotent: pausing a
        paused Run returns True without a duplicate row.
        """
        if reason not in ("human pause", "Steer pause"):
            return False
        if self.is_paused(trace_id):
            return True
        with self._lock:
            live = self._live.pop(trace_id, {})
            live_dests = [dest for dest in live.values() if dest]
        last = db_module.last_attempt(self.conn, trace_id)
        if live_dests:
            # Live tunnel first: an open tunnel has no journal row yet,
            # so the journal lookup would come back empty. Journaled
            # destination second, never empty for a live tunnel.
            dest_host = endpoint = live_dests[0]
        elif last:
            dest_host = last["dest_host"]
            endpoint = last["endpoint"]
        else:
            dest_host = endpoint = ""
        method = last["method"] if last else ""
        now = datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds")
        db_module.save_paused(self.conn, trace_id, reason, now)
        self._control_row(trace_id, method, dest_host, endpoint,
                          "unknown", "paused", reason, "paused")
        with self._lock:
            self._paused[trace_id] = {"reason": reason, "created_at": now}
            self._verified.pop(trace_id, None)
        for sock in live:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        return True

    def red_button(self, reason: str = "human red button") -> bool:
        """Stop all Runs at once. Journal first, then cut everything.

        Human-only: a plain method on the local proxy state, never an
        HTTP route, so proxied agent traffic cannot call it. Every known
        Run gets a stop row first (outcome stopped, status unknown:
        Unverified explicitly), then every live tunnel on every Run is
        cut. Paused Runs get a stop row too. The journal is only added
        to, never deleted. Fresh approvals and Verifies are cleared, so
        nothing restarts without a fresh human word. Every press is
        journaled: audit everything, never silently.
        """
        if reason not in ("human red button", "Steer red button"):
            return False
        journaled = [row[0] for row in self.conn.execute(
            "SELECT DISTINCT trace_id FROM attempts").fetchall()]
        with self._lock:
            # Open tunnels have no journal row yet: their rows land when
            # the tunnels end. They are known Runs too, and stop as well.
            live_only = [t for t in self._live if t not in journaled]
        traces = journaled + live_only
        now = datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds")
        db_module.save_red_button(self.conn, reason, now)
        db_module.save_red_button_traces(self.conn, traces)
        with self._lock:
            self._stopped_traces.update(traces)
        for trace_id in traces:
            # Live first, journaled second, never empty for a live
            # tunnel: an open tunnel has no journal row yet. Same union
            # rule as Pause, fix 54498fc.
            with self._lock:
                live_here = self._live.get(trace_id, {})
                live_dests = [d for d in live_here.values() if d]
            last = db_module.last_attempt(self.conn, trace_id)
            if live_dests:
                dest_host = endpoint = live_dests[0]
            elif last:
                dest_host = last["dest_host"]
                endpoint = last["endpoint"]
            else:
                dest_host = endpoint = ""
            method = last["method"] if last else ""
            self._control_row(trace_id, method, dest_host, endpoint,
                              "unknown", "stopped", reason, "stopped")
        with self._lock:
            self._stopped = {"reason": reason, "created_at": now}
            self._verified.clear()
            self._approved.clear()
            live = [sock for socks in self._live.values() for sock in socks]
            self._live.clear()
        for sock in live:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        return True

    def approve_run(self, trace_id: str, done_clause=None) -> bool:
        """Fresh human approval for a NEW Run after Red button.

        Human-only: a plain method on the local proxy state, never an
        HTTP route. Refuses (False, no row) when the done clause is
        missing or not human-approved, or when the trace was stopped by
        the button: old Runs stay stopped and never restart on their
        own. Otherwise journals the approval and records it. Approval
        alone moves no bytes; a fresh Verify must still follow.
        """
        if (not isinstance(done_clause, dict)
                or done_clause.get("approved_by") != "human"
                or not done_clause.get("read_back")):
            return False
        with self._lock:
            if trace_id in self._stopped_traces:
                return False
        now = datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds")
        self._control_row(trace_id, "APPROVE", "", "",
                          "unknown", "", "fresh approval recorded",
                          "stopped")
        with self._lock:
            self._approved[trace_id] = now
        return True

    def red_gate(self, trace_id: str) -> bool:
        """True when this trace may move bytes right now.

        With no Red button pressed, everything passes. After the button,
        only a trace with a fresh human approval plus a fresh Verify
        passes. Old and unseen Runs are refused until then: no fail-open.
        """
        with self._lock:
            if self._stopped is None:
                return True
            approved_at = self._approved.get(trace_id)
            verified_at = self._verified.get(trace_id)
            return bool(approved_at and verified_at
                        and verified_at >= approved_at)

    def verify_run(self, trace_id: str, done_clause=None) -> bool:
        """Record a fresh human Verify for a paused, redirected, or
        Red-button-approved Run.

        Refuses (False, no row) when the Run is neither paused nor
        redirected nor approved after Red button, when the done clause
        is missing or not human-approved, or when the journal read finds
        nothing to verify. Otherwise journals the Verify and stamps it:
        only a Verify after the pause, redirect, or fresh approval
        unblocks a retry.
        """
        with self._lock:
            gated = (trace_id in self._paused
                     or trace_id in self._redirects
                     or (self._stopped is not None
                         and trace_id in self._approved))
        if not gated:
            return False
        if (not isinstance(done_clause, dict)
                or done_clause.get("approved_by") != "human"
                or not done_clause.get("read_back")):
            return False
        last = db_module.last_attempt(self.conn, trace_id)
        if last is None:
            return False
        self._control_row(trace_id, "VERIFY", last["dest_host"],
                          last["endpoint"], "unknown", "", "verify ok",
                          "paused")
        with self._lock:
            self._verified[trace_id] = datetime.datetime.now(
                datetime.timezone.utc).isoformat(timespec="seconds")
        return True

    def retry_run(self, trace_id: str) -> tuple:
        """Retry gate: blocked until fresh, everywhere it applies.

        Returns (allowed, reason). A blocked retry is journaled: reason
        "verify required before retry", or "red button stopped" for an
        old Run with no fresh approval. An allowed retry (fresh Verify
        after the pause, redirect, or Red-button approval) resumes the
        Run and journals that. A pause is forgotten on resume; a redirect
        stays on its human-chosen destination, and the Verify stamp stays
        with it so later retries keep working until the next redirect; a
        Red-button approval and Verify stand until the next press. A Run
        that is gated nowhere is not gated here: (True, "not paused") or
        (True, "approved") for a fresh Red-button Run, no row.
        """
        with self._lock:
            approved_at = self._approved.get(trace_id)
            verified_at = self._verified.get(trace_id)
            if trace_id in self._paused:
                kind, since = "paused", self._paused[trace_id]["created_at"]
            elif trace_id in self._redirects:
                kind = "redirected"
                since = self._redirects[trace_id]["created_at"]
            elif self._stopped is not None and not (
                    approved_at and verified_at and verified_at >= approved_at):
                kind, since = "stopped", self._stopped["created_at"]
            else:
                if self._stopped is not None:
                    return True, "approved"
                return True, "not paused"
        last = db_module.last_attempt(self.conn, trace_id)
        dest_host = last["dest_host"] if last else ""
        endpoint = last["endpoint"] if last else ""
        # The stamp can only exist when a Verify landed after this
        # pause, redirect, or Red-button press (a new one clears it), so
        # presence means fresh. The timestamp check is a backstop,
        # same-second stamps included.
        if not verified_at or verified_at < since:
            if kind == "stopped" and not approved_at:
                reason = "red button stopped"
            else:
                reason = "verify required before retry"
            self._control_row(trace_id, "RETRY", dest_host, endpoint,
                              "unknown", "blocked", reason, kind)
            return False, reason
        if kind == "paused":
            db_module.clear_paused(self.conn, trace_id)
        now = datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds")
        self._control_row(trace_id, "RETRY", dest_host, endpoint,
                          "unknown", "", "retry allowed after verify",
                          kind)
        with self._lock:
            if kind == "paused":
                self._paused.pop(trace_id, None)
                self._verified.pop(trace_id, None)
            elif kind == "redirected":
                self._verified[trace_id] = now
        return True, "retry allowed after verify"

    def verify_read_back(self, trace_id: str, claim,
                           done_clause=None):
        """Verify a claim by independent local read-back. Journal first.

        Returns (verdict, card) with verdict one of Correct, Incorrect,
        Unverified. Local file and SQLite only: reads the real effect
        after close/fsync and COMMIT, never the agent's own word. No
        scores, no LLM, no percentages. The call row is journaled before
        anything is read; the verdict row follows; a stop follows an
        Incorrect verdict. Verdict and retry permission stay separate:
        nothing here stamps a Verify or allows a retry.
        """
        now = datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds")
        key = (claim.get("idempotency_key", "-")
               if isinstance(claim, dict) else "-")
        self._control_row(trace_id, "VERIFY", "", "", "unknown",
                          "verified", f"verify call {key}", "verified")
        verdict, what_read, source, why, nxt = self._read_back(claim,
                                                               done_clause)
        status = {"Correct": "success", "Incorrect": "failure",
                  "Unverified": "unknown"}[verdict]
        self._control_row(trace_id, "VERIFY", "", "", status,
                          "verified", f"verify {verdict}", "verified")
        if verdict == "Incorrect":
            self.pause_run(trace_id, reason="Steer pause")
        card = {"claim": claim, "what_read": what_read, "source": source,
                "as_of": now, "verdict": verdict, "why": why, "next": nxt}
        return verdict, card

    def _read_back(self, claim, done_clause):
        """Independent read of the claimed effect. No journal here.

        Returns (verdict, what_read, source, why, next). Anything that
        cannot be read, has no approved done, or is remote with no local
        proof is Unverified, never Incorrect: addressing and credential
        errors are excluded, not contradicted.
        """
        if (not isinstance(done_clause, dict)
                or done_clause.get("approved_by") != "human"
                or not done_clause.get("read_back")):
            return ("Unverified", "no read attempted",
                    "journal: no approved done clause",
                    "no approved done clause",
                    "human approves the done clause, then Verify again")
        if not isinstance(claim, dict):
            return ("Unverified", "no read attempted",
                    "journal: claim is not a read profile",
                    "no read profile for this claim",
                    "human approves a read profile, then Verify again")
        kind = claim.get("kind")
        if kind == "local-file":
            return self._read_back_file(claim)
        if kind == "sqlite":
            return self._read_back_sqlite(claim)
        return ("Unverified", "no read attempted",
                "journal: remote effect with no local proof",
                "remote with no local proof",
                "human confirms, or add a local proof, then Verify again")

    def _read_back_file(self, claim):
        """Strong local file read: the bytes on disk, after fsync."""
        path = claim.get("path", "")
        expected = claim.get("expected_text")
        what = f"local file {path}"
        try:
            with open(path, "r") as handle:
                actual = handle.read()
        except FileNotFoundError:
            return ("Incorrect", what, "local filesystem",
                    "file does not exist",
                    "Run stopped, human reviews the claim")
        except OSError:
            return ("Unverified", what, "local filesystem",
                    "file could not be read",
                    "human checks the file, then Verify again")
        if actual == expected:
            return ("Correct", what, "local filesystem",
                    "file text matched the claim",
                    "done, keep the journal")
        return ("Incorrect", what, "local filesystem",
                "file text contradicted the claim",
                "Run stopped, human reviews the claim")

    def _read_back_sqlite(self, claim):
        """Strong SQLite read: SELECT in a fresh txn, after COMMIT."""
        path = claim.get("db", "")
        what = f"local SQLite {path}"
        if not path or not os.path.exists(path):
            return ("Incorrect", what, "local SQLite",
                    "database file does not exist",
                    "Run stopped, human reviews the claim")
        try:
            conn = sqlite3.connect(path)
            try:
                rows = conn.execute(
                    claim.get("sql", ""),
                    claim.get("params", []) or []).fetchall()
            finally:
                conn.close()
        except sqlite3.Error:
            return ("Unverified", what, "local SQLite",
                    "read failed, not a contradiction",
                    "human checks the database, then Verify again")
        actual = [list(row) for row in rows]
        if actual == (claim.get("expected_rows") or []):
            return ("Correct", what, "local SQLite",
                    "row matched the claim in a fresh transaction",
                    "done, keep the journal")
        return ("Incorrect", what, "local SQLite",
                "row missing in a fresh transaction",
                "Run stopped, human reviews the claim")

    def _register_live(self, trace_id: str, sock, dest_label: str = "") -> None:
        """Track one open tunnel socket under its Run, for Pause cuts.

        The destination label rides along because an open tunnel has no
        journal row yet: a later Pause must journal where the live Run
        actually is, never an empty string.
        """
        with self._lock:
            self._live.setdefault(trace_id, {})[sock] = dest_label

    def _unregister_live(self, trace_id: str, sock) -> None:
        """Forget a closed tunnel socket. Never raises."""
        with self._lock:
            live = self._live.get(trace_id)
            if live is not None:
                live.pop(sock, None)
                if not live:
                    self._live.pop(trace_id, None)


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

            if not state.red_gate(trace_id):
                # Red button is on and this trace has no fresh human
                # approval plus Verify: no new tunnel. Unknown, never
                # Correct. Nothing fails open.
                attempt = state.peek_attempt(trace_id, endpoint, "CONNECT")
                log_connect("unknown", "stopped",
                            "approval required after red button",
                            503, 0, 0, "stopped")
                self.send_response(503)
                self.send_header("X-Trace-Id", trace_id)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if not state.is_allowed(dest_host, dest_port):
                attempt = state.peek_attempt(trace_id, endpoint, "CONNECT")
                log_connect("blocked", "blocked", "not_allowlisted", 403,
                            0, 0, "blocked_allowlist")
                self.send_response(403)
                self.send_header("X-Trace-Id", trace_id)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            target = state.redirect_target(trace_id)
            if target is not None:
                # Redirected Run: this tunnel goes to the human-chosen
                # destination instead of the requested one. The target
                # was allowlisted at redirect time.
                try:
                    new_host, new_port = _split_authority(target, 443)
                except ValueError:
                    pass  # validated at redirect time; keep requested
                else:
                    dest_host, dest_port = new_host, new_port
                    endpoint = target
            if not state.check_rate(endpoint):
                attempt = state.peek_attempt(trace_id, endpoint, "CONNECT")
                log_connect("rate_limited", "rate_limited", "rate_limited",
                            429, 0, 0, "rate_limited")
                self.send_response(429)
                self.send_header("X-Trace-Id", trace_id)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if state.is_paused(trace_id):
                # Paused Run: no new tunnel. Unknown, never Correct.
                attempt = state.peek_attempt(trace_id, endpoint, "CONNECT")
                log_connect("unknown", "paused",
                            state.pause_reason(trace_id),
                            503, 0, 0, "paused")
                self.send_response(503)
                self.send_header("X-Trace-Id", trace_id)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            rule = state.override_rule(endpoint)
            if rule is not None and rule["action"] == "pause":
                # Overridden network: no new tunnel. Unknown, never
                # Correct. Journaled under paused, like a Run pause.
                attempt = state.peek_attempt(trace_id, endpoint, "CONNECT")
                log_connect("unknown", "paused", rule["reason"],
                            503, 0, 0, "paused")
                self.send_response(503)
                self.send_header("X-Trace-Id", trace_id)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            cap = state.cap_rule(endpoint)
            if cap is not None:
                total = state.capped_total(endpoint)
                if total >= cap["cap"]:
                    # At the cap: journal the block first, cut live
                    # tunnels second, then refuse. Unknown, never
                    # Correct. Retries stay blocked until a fresh Verify.
                    attempt = state.peek_attempt(trace_id, endpoint, "CONNECT")
                    log_connect("unknown", "blocked", "cap block 100%",
                                503, 0, 0, "capped")
                    state._cap_block(endpoint)
                    self.send_response(503)
                    self.send_header("X-Trace-Id", trace_id)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if total >= 0.8 * cap["cap"]:
                    with state._lock:
                        fresh = endpoint not in state._cap_warned
                        if fresh:
                            state._cap_warned.add(endpoint)
                    if fresh:
                        # Warn once per cap: the run continues, the next
                        # call still flows. The row carries what was
                        # spent: saying it is the warning.
                        state._control_row(
                            trace_id, "CONNECT", endpoint, endpoint,
                            "unknown", "warned", "cap warn 80%", "warned",
                            total)

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

            # Register before answering: by the time the client sees the
            # 200, the tunnel is tracked, so a Pause that lands in between
            # journals the live destination and cuts a live socket.
            state._register_live(trace_id, self.connection, endpoint)
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
                state._unregister_live(trace_id, self.connection)
                upstream.close()
            cut = state.steer_cut(trace_id)
            if cut is not None and status != "success":
                # Cut mid-flight by Pause or Redirect: the tunnel did not
                # fail, it was steered, so the outcome is unknown, never
                # failure. The reason stays the steer reason, for one
                # plain story.
                status = "unknown"
                log_connect(status, cut[0], cut[1], None,
                            bytes_in, bytes_out, close_reason, connect_ms)
            else:
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
                     body, trace_id=None, close_reason="unknown",
                     outcome=None):
            """Refuse a request with a plain-words body plus an audit row.

            Outcome defaults to the status (blocked, rate_limited,
            failure); Pause passes its own outcome so a paused refusal
            reconciles under paused instead of failure.
            """
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
                http_status=code,
                outcome=outcome if outcome is not None else status,
                reason=reason,
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
            if not state.red_gate(trace_id):
                # Red button is on and this trace has no fresh human
                # approval plus Verify: nothing forwards. Unknown, never
                # Correct. Nothing fails open.
                self._refused(
                    503, "unknown", "approval required after red button",
                    dest_label, endpoint,
                    b"stopped: Red button is on, "
                    b"a fresh approval plus Verify is needed\n",
                    trace_id=trace_id, close_reason="stopped",
                    outcome="stopped")
                return
            if not state.is_allowed(dest_host, dest_port):
                reject(403, "blocked", "not_allowlisted",
                       close_reason="blocked_allowlist")
                return
            target = state.redirect_target(trace_id)
            if target is not None:
                # Redirected Run: this request goes to the human-chosen
                # destination instead of the requested one. The target
                # was allowlisted at redirect time. The path stays.
                try:
                    new_host, new_port = _split_authority(target, 80)
                except ValueError:
                    pass  # validated at redirect time; keep requested
                else:
                    dest_host, dest_port = new_host, new_port
                    dest_label = target
            if not state.check_rate(dest_label):
                reject(429, "rate_limited", "rate_limited",
                       close_reason="rate_limited")
                return
            if state.is_paused(trace_id):
                # Paused Run: nothing forwards for it. Unknown, never
                # Correct, and reconciled under paused, not failure.
                self._refused(
                    503, "unknown", state.pause_reason(trace_id),
                    dest_label, endpoint,
                    b"paused: this Run is paused, "
                    b"retry needs a fresh Verify\n",
                    trace_id=trace_id, close_reason="paused",
                    outcome="paused")
                return
            rule = state.override_rule(dest_label)
            if rule is not None and rule["action"] == "pause":
                # Overridden network: nothing forwards for it. Unknown,
                # never Correct, and reconciled under paused, not failure.
                self._refused(
                    503, "unknown", rule["reason"],
                    dest_label, endpoint,
                    b"paused: this network is paused by human override, "
                    b"retry needs a fresh Verify\n",
                    trace_id=trace_id, close_reason="paused",
                    outcome="paused")
                return
            cap = state.cap_rule(dest_label)
            if cap is not None:
                total = state.capped_total(dest_label)
                if total >= cap["cap"]:
                    # At the cap: journal the block first, cut live
                    # tunnels second, then refuse. Unknown, never
                    # Correct. This run stops unless a human verifies
                    # everything is fine.
                    self._refused(
                        503, "unknown", "cap block 100%",
                        dest_label, endpoint,
                        b"blocked: spend cap reached. This run stops unless "
                        b"a human verifies everything is fine.\n",
                        trace_id=trace_id, close_reason="capped",
                        outcome="blocked")
                    state._cap_block(dest_label)
                    return
                if total >= 0.8 * cap["cap"]:
                    with state._lock:
                        fresh = dest_label not in state._cap_warned
                        if fresh:
                            state._cap_warned.add(dest_label)
                    if fresh:
                        state._control_row(
                            trace_id, self.command, dest_label, endpoint,
                            "unknown", "warned", "cap warn 80%", "warned",
                            total)

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
