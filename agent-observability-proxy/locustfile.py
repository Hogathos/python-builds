"""Locust load: steady GETs + burst past 100/10s + recovery, via the proxy.

Self-contained: starts the local test server and the proxy in-process on
test start, runs three stages (steady 10s, burst 12s, recovery 16s),
then prints a verdict: req/s, p50/p95 latency, failure rate, 429
presence during the burst, the exact second requests start passing
again, and attempts.db outcome counts. Exit code 1 on any failed check.

Local hosts only. No production code is touched.

Run:
  .venv\\Scripts\\locust -f locustfile.py --headless
"""
import os
import random
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import proxy as proxy_module
import server as server_module
from locust import HttpUser, LoadTestShape, between, events, task

ECHO_PORT = int(os.environ.get("ECHO_PORT", "18080"))
PROXY_PORT = int(os.environ.get("PROXY_PORT", "8888"))
LOAD_DB = os.environ.get("LOAD_DB", "load_http.db")
TARGET = f"http://127.0.0.1:{ECHO_PORT}/echo"
PROXIES = {"http": f"http://127.0.0.1:{PROXY_PORT}"}

STEADY_END = 10.0
BURST_END = 22.0
RUN_END = 38.0

_records = []  # (epoch_seconds, status_or_None, latency_seconds)
_records_lock = threading.Lock()
_t0 = [0.0]
_wall0 = [0.0]
_infra = {}
_infra_error = [""]


def _record(status, latency):
    with _records_lock:
        _records.append((time.time(), status, latency))


def _phase_wait(*args):
    elapsed = time.monotonic() - _t0[0]
    if elapsed < STEADY_END:
        return random.uniform(0.5, 1.0)
    if elapsed < BURST_END:
        return random.uniform(0.02, 0.1)
    return random.uniform(0.5, 1.0)


class ProxyUser(HttpUser):
    host = f"http://127.0.0.1:{ECHO_PORT}"
    wait_time = _phase_wait

    def on_start(self):
        self.client.trust_env = False

    @task
    def echo(self):
        t0 = time.monotonic()
        try:
            with self.client.get(TARGET, proxies=PROXIES,
                                 catch_response=True) as resp:
                _record(resp.status_code, time.monotonic() - t0)
                if resp.status_code in (200, 429):
                    resp.success()
                else:
                    resp.failure(f"unexpected status {resp.status_code}")
        except Exception:
            _record(None, time.monotonic() - t0)
            raise
        finally:
            # Fresh connection per request: pooled keep-alive would pile
            # idle handler threads on the in-process servers at shutdown.
            self.client.close()


class Stages(LoadTestShape):
    stages = [
        {"duration": STEADY_END, "users": 5, "spawn_rate": 5},
        {"duration": BURST_END, "users": 40, "spawn_rate": 40},
        {"duration": RUN_END, "users": 2, "spawn_rate": 5},
    ]

    def tick(self):
        if _infra_error[0]:
            return None
        run_time = self.get_run_time()
        for stage in self.stages:
            if run_time < stage["duration"]:
                return (stage["users"], stage["spawn_rate"])
        return None


def _wait_ready():
    import urllib.request
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(TARGET, timeout=2) as resp:
                if resp.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("echo server never became ready")


def _require_free_port(host, port, what):
    # A plain bind (no SO_REUSEADDR) fails if anyone listens here. Never
    # share the port: on Windows a second listener silently steals traffic.
    import socket
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
    except OSError:
        raise SystemExit(
            f"error: {what} port {port} is already in use; stop the other "
            f"process or set a free port")
    finally:
        probe.close()


@events.test_start.add_listener
def _start_infra(environment, **kwargs):
    try:
        if os.path.exists(LOAD_DB):
            os.remove(LOAD_DB)
        _require_free_port("127.0.0.1", ECHO_PORT, "echo server")
        _require_free_port("127.0.0.1", PROXY_PORT, "proxy")
        echo = ThreadingHTTPServer(("127.0.0.1", ECHO_PORT), server_module.Handler)
        threading.Thread(target=echo.serve_forever, daemon=True).start()
        proxy = proxy_module.serve("127.0.0.1", PROXY_PORT, LOAD_DB)
        threading.Thread(target=proxy.serve_forever, daemon=True).start()
        _infra["echo"] = echo
        _infra["proxy"] = proxy
        _wait_ready()
        _t0[0] = time.monotonic()
        _wall0[0] = time.time()
    except BaseException as exc:
        _infra_error[0] = f"{type(exc).__name__}: {exc}"


def _percentile(sorted_vals, pct):
    if not sorted_vals:
        return 0.0
    return sorted_vals[min(int(pct * len(sorted_vals)), len(sorted_vals) - 1)]


@events.quitting.add_listener
def _verdict(environment, **kwargs):
    with _records_lock:
        records = list(_records)
    failures = []

    def check(name, ok, detail=""):
        print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}".rstrip(),
              flush=True)
        if not ok:
            failures.append(name)

    check("infra started", not _infra_error[0], _infra_error[0])
    total = len(records)
    elapsed = (records[-1][0] - records[0][0]) if total > 1 else 0.0
    lats = sorted(lat for _, status, lat in records
                  if status in (200, 429))
    errors = sum(1 for _, status, _ in records
                 if status is None or status == 0)
    unexpected = [s for _, s, _ in records
                  if s is not None and s not in (0, 200, 429)]
    # Verdict windows in epoch terms, anchored at test start.
    wall_start = _wall0[0] or time.time()
    burst_429s = sum(1 for t, s, _ in records
                     if wall_start + STEADY_END <= t < wall_start + BURST_END
                     and s == 429)
    first_pass = next((t for t, s, _ in records
                       if t > wall_start + BURST_END and s == 200), None)
    recovered = sum(1 for t, s, _ in records
                    if t > wall_start + BURST_END + 10.0 and s == 200)

    print(f"requests={total} elapsed={elapsed:.1f}s "
          f"req/s={total / elapsed:.1f}" if elapsed else "requests=0",
          flush=True)
    print(f"p50={_percentile(lats, 0.50):.3f}s "
          f"p95={_percentile(lats, 0.95):.3f}s "
          f"errors={errors} unexpected={len(unexpected)}", flush=True)
    counts = {"allowed": 0, "blocked": 0, "rate_limited": 0, "other": 0}
    if os.path.exists(LOAD_DB):
        conn = sqlite3.connect(LOAD_DB)
        for outcome, n in conn.execute(
                "SELECT outcome, COUNT(*) FROM attempts GROUP BY outcome"):
            if outcome in counts:
                counts[outcome] = n
        conn.close()
    print(f"db outcomes: allowed={counts['allowed']} "
          f"blocked={counts['blocked']} "
          f"rate_limited={counts['rate_limited']}", flush=True)

    check("got traffic", total > 100, f"({total} requests)")
    check("no transport errors", errors == 0, f"({errors})")
    check("no unexpected statuses", not unexpected,
          f"({sorted(set(unexpected))})" if unexpected else "")
    check("429s during burst", burst_429s > 0, f"({burst_429s})")
    if first_pass is not None:
        clock = datetime.fromtimestamp(first_pass, timezone.utc)
        check("requests pass after burst", True,
              f"(first 200 at {clock.strftime('%H:%M:%S')} UTC)")
    else:
        check("requests pass after burst", False, "(no 200 after burst end)")
    check("sustained recovery after window", recovered >= 5, f"({recovered})")
    check("db shows rate limiting", counts["rate_limited"] > 0,
          f"({counts['rate_limited']} rows)")

    # No server shutdown: under gevent it hangs, and the verdict is in.
    # Daemon serve threads die with the process; every request already
    # closed its connection, so no handler threads linger.
    try:
        _infra["proxy"].state.conn.close()
    except Exception:
        pass
    if failures:
        environment.process_exit_code = 1
