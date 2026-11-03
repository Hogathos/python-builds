"""Layer 2 scorer v1: replay the golden dataset against the local proxy.

In-process, loopback only, temp SQLite per case (same style as the
demos/tests). Compares actual SQLite rows to each case's expected
outputs, prints PASS/FAIL per case plus a per-category summary, and
exits non-zero if any case fails.

Run:  python evals/scorer.py --dataset evals/golden_dataset_v1.json
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import socket
import socketserver
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import agent_b as agent_b_module
import db as db_module
import proxy as proxy_module
import server as server_module


class _Echo(socketserver.BaseRequestHandler):
    def handle(self):
        while True:
            data = self.request.recv(65536)
            if not data:
                return
            self.request.sendall(data)


class Env:
    """One isolated replay world: upstream, echo, proxy, optional B."""

    def __init__(self, **proxy_kwargs):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "attempts.db")
        self.upstream = ThreadingHTTPServer(("127.0.0.1", 0), server_module.Handler)
        self.upstream_port = self.upstream.server_address[1]
        self.echo = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Echo)
        self.echo_port = self.echo.server_address[1]
        self.proxy = proxy_module.serve("127.0.0.1", 0, self.db_path, **proxy_kwargs)
        self.proxy_port = self.proxy.server_address[1]
        self.agent_b = None
        for srv in (self.upstream, self.echo, self.proxy):
            threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler(
            {"http": f"http://127.0.0.1:{self.proxy_port}"}))

    def with_agent_b(self):
        self.agent_b = agent_b_module.serve(
            "127.0.0.1", 0,
            proxy_url=f"http://127.0.0.1:{self.proxy_port}",
            upstream_base=f"http://127.0.0.1:{self.upstream_port}")
        threading.Thread(target=self.agent_b.serve_forever, daemon=True).start()
        return self.agent_b.server_address[1]

    def rows(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        out = conn.execute("SELECT * FROM attempts ORDER BY id").fetchall()
        conn.close()
        return out

    def dump(self):
        return "\n".join(str(r) for r in self.rows())

    def http(self, url, method="GET", trace=None, data=None, headers=None):
        req = urllib.request.Request(url, data=data, method=method)
        if trace:
            req.add_header("X-Trace-Id", trace)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with self.opener.open(req, timeout=10) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def connect_raw(self, dest, trace=None):
        sock = socket.create_connection(("127.0.0.1", self.proxy_port), timeout=5)
        lines = [f"CONNECT {dest} HTTP/1.1", f"Host: {dest}"]
        if trace:
            lines.append(f"X-Trace-Id: {trace}")
        sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        raw = b""
        while b"\r\n\r\n" not in raw:
            chunk = sock.recv(65536)
            if not chunk:
                break
            raw += chunk
        head = raw.split(b"\r\n\r\n", 1)[0].decode(errors="replace")
        status = int(head.split()[1]) if head.split() else 0
        hdrs = {}
        for line in head.split("\r\n")[1:]:
            if ": " in line:
                k, v = line.split(": ", 1)
                hdrs[k.lower()] = v
        return sock, status, hdrs

    def close(self):
        if self.agent_b:
            self.agent_b.shutdown(); self.agent_b.server_close()
        self.proxy.shutdown(); self.echo.shutdown(); self.upstream.shutdown()
        self.proxy.server_close(); self.echo.server_close(); self.upstream.server_close()
        self.proxy.state.conn.close()
        self.tmp.cleanup()


def _check(case, env, actual):
    """Return list of failure strings (empty = pass). Never prints secrets."""
    exp = case["expected"]
    fails = []
    rows = actual["rows"]

    def need(cond, msg):
        if not cond:
            fails.append(msg)

    if "http_status" in exp and actual.get("status") is not None:
        need(actual["status"] == exp["http_status"],
             f"http_status {actual['status']} != {exp['http_status']}")
    if "statuses" in exp:
        need(actual.get("statuses") == exp["statuses"],
             f"statuses {actual.get('statuses')} != {exp['statuses']}")
    if "rows" in exp:
        relevant = actual.get("relevant_rows", rows)
        need(len(relevant) == exp["rows"],
             f"rows {len(relevant)} != {exp['rows']}")
    if "trace_id" in exp:
        need(any(r["trace_id"] == exp["trace_id"] for r in rows),
             "expected trace_id not found in rows")
    if exp.get("generated_trace_returned"):
        gen = actual.get("response_trace")
        need(bool(gen), "no generated trace returned")
        need(any(r["trace_id"] == gen for r in rows),
             "generated trace not in rows")
    if "distinct_trace_ids" in exp:
        need(len({r["trace_id"] for r in rows}) == exp["distinct_trace_ids"],
             "distinct trace_id count mismatch")
    if "distinct_task_numbers" in exp:
        need(len({r["task_number"] for r in rows}) == exp["distinct_task_numbers"],
             "distinct task_number count mismatch")
    if "legs" in exp:
        need(any(r["endpoint"] == exp["legs"]["a_endpoint"] for r in rows),
             "A leg (/task) missing")
        need(any(r["endpoint"] == exp["legs"]["b_endpoint"] for r in rows),
             "B leg (/echo) missing")
    for key, field in (("row_status", "status"), ("outcome", "outcome"),
                       ("reason", "reason"), ("method", "method"),
                       ("endpoint", "endpoint")):
        if key in exp:
            col = field
            need(all(r[col] == exp[key] for r in actual.get("relevant_rows", rows)),
                 f"{col} != {exp[key]} on some row")
    if "cost_dollars" in exp:
        need(all(float(r["cost_dollars"]) == exp["cost_dollars"] for r in rows),
             "cost_dollars mismatch (cost must never be invented)")
    if exp.get("zero_forwarded_bytes"):
        need(all(r["bytes_in"] == 0 and r["bytes_out"] == 0
                 for r in actual.get("relevant_rows", rows)),
             "blocked/failed rows must have zero forwarded bytes")
    if "bytes_in_min" in exp:
        need(any(r["bytes_in"] >= exp["bytes_in_min"] for r in rows),
             "bytes_in below minimum")
    if "bytes_out_min" in exp:
        need(any(r["bytes_out"] >= exp["bytes_out_min"] for r in rows),
             "bytes_out below minimum")
    if exp.get("latency_present"):
        need(all(r["latency_seconds"] >= 0 for r in rows), "latency missing")
    if exp.get("echo_matches"):
        need(actual.get("echo_ok") is True, "tunnel echo did not match")
    if "outcome_counts" in exp:
        conn = _conn(env)
        try:
            counts = db_module.fetch_outcome_counts(conn)
        finally:
            conn.close()
        for key, want in exp["outcome_counts"].items():
            need(counts.get(key, 0) == want,
                 f"outcome {key}: {counts.get(key, 0)} != {want}")
        if exp.get("outcome_sum_equals_attempts"):
            need(sum(counts.values()) == len(rows),
                 "outcome counts do not add up to total attempts")
    if exp.get("secrets_absent_from_dump"):
        dump = env.dump()
        for secret in actual.get("secrets", []):
            need(secret not in dump, "a secret value appears in the SQLite dump")
    return fails


def _conn(env):
    conn = sqlite3.connect(env.db_path)
    return conn


def replay(case, env):
    """Execute one case's scenario; return actuals for _check."""
    sc = case["scenario"]
    kind = sc["type"]
    trace = sc.get("trace_id")
    actual = {"rows": [], "relevant_rows": [], "status": None, "secrets": []}
    upstream = f"http://127.0.0.1:{env.upstream_port}"

    if kind == "http":
        dest = upstream if sc["destination"] == "upstream" else f"http://{sc['destination']}"
        headers = {}
        data = None
        if sc.get("secret_body"):
            data = sc["secret_body"].encode()
            actual["secrets"] += [sc["secret_body"], sc["secret_key"],
                                  sc["authorization"]]
            headers["Authorization"] = sc["authorization"]
        status, hdrs, _ = env.http(f"{dest}{sc['endpoint']}", sc.get("method", "GET"),
                                   trace=trace, data=data, headers=headers or None)
        actual.update(status=status, response_trace=hdrs.get("X-Trace-Id"))
        actual["rows"] = env.rows()
        actual["relevant_rows"] = [r for r in actual["rows"]
                                   if trace is None or r["trace_id"] == trace
                                   or r["trace_id"] == actual["response_trace"]]
        if trace is None:
            actual["relevant_rows"] = actual["rows"]
    elif kind == "connect_echo":
        payload = b"golden-tunnel-payload-0123456789"
        sock, status, _ = env.connect_raw(f"127.0.0.1:{env.echo_port}", trace)
        echoed = b""
        if status == 200:
            sock.sendall(payload)
            while len(echoed) < len(payload):
                echoed += sock.recv(65536)
        sock.close()
        time.sleep(0.3)
        actual.update(status=status, echo_ok=(echoed == payload))
        actual["rows"] = env.rows()
        actual["relevant_rows"] = actual["rows"]
    elif kind in ("connect_closed_port", "connect_raw"):
        if kind == "connect_closed_port":
            tmp = socket.socket(); tmp.bind(("127.0.0.1", 0))
            dest = f"127.0.0.1:{tmp.getsockname()[1]}"; tmp.close()
        else:
            dest = sc["destination"]
        sock, status, _ = env.connect_raw(dest, trace)
        sock.close()
        time.sleep(0.3)
        actual.update(status=status)
        actual["rows"] = env.rows()
        actual["relevant_rows"] = actual["rows"]
    elif kind == "two_agent":
        b_port = env.with_agent_b()
        status, hdrs, _ = env.http(f"http://127.0.0.1:{b_port}/task", trace=trace)
        actual.update(status=status, response_trace=hdrs.get("X-Trace-Id"))
        actual["rows"] = [r for r in env.rows() if r["trace_id"] == trace]
        actual["relevant_rows"] = actual["rows"]
    elif kind == "burst":
        statuses = []
        for i in range(sc["burst_count"]):
            s, _, _ = env.http(f"{upstream}{sc['endpoint']}",
                               trace=f"{trace or 'burst'}-{i}")
            statuses.append(s)
        if sc.get("recovery_call"):
            time.sleep(sc.get("pause_seconds", 1.2))
            s, _, _ = env.http(f"{upstream}{sc['endpoint']}", trace="burst-recovery")
            statuses.append(s)
        actual.update(statuses=statuses)
        actual["rows"] = env.rows()
        actual["relevant_rows"] = actual["rows"]
    elif kind == "outcome_accounting":
        conn = db_module.init_db(env.db_path)
        for i in range(sc.get("seed_legacy_rows", 0)):
            db_module.log_attempt(conn, trace_id=f"legacy-{i}", task_number=90 + i,
                                  attempt=1, status="success")
        conn.close()
        env.http(f"{upstream}/echo", trace=trace)
        env.http("http://exfil.example.test/echo", method="POST", trace=f"{trace}-blocked")
        actual["rows"] = env.rows()
        actual["relevant_rows"] = actual["rows"]
    else:
        raise ValueError(f"unknown scenario type: {kind}")
    return actual


def run_dataset(dataset_path):
    with open(dataset_path, encoding="utf-8") as fh:
        dataset = json.load(fh)
    results = []
    lines = []
    for case in dataset["cases"]:
        kwargs = {}
        sc = case["scenario"]
        if sc["type"] == "burst":
            kwargs = {"rate_limit": sc["rate_limit"],
                      "rate_window": sc["rate_window_seconds"]}
        env = Env(**kwargs)
        try:
            actual = replay(case, env)
            fails = _check(case, env, actual)
            # Scorer output must never contain the case's secrets either.
            if case["expected"].get("secrets_absent_from_output"):
                joined = "\n".join(lines)
                for secret in actual.get("secrets", []):
                    if secret in joined:
                        fails.append("a secret value appears in scorer output")
        except Exception as exc:  # scorer must report, not crash
            fails = [f"replay error: {type(exc).__name__}"]
        finally:
            env.close()
        ok = not fails
        results.append((case, ok, fails))
        lines.append(f"[{'PASS' if ok else 'FAIL'}] {case['id']} "
                     f"({case['milestone']}/{case['category']})"
                     + ("" if ok else f" -- {'; '.join(fails)}"))
    by_cat = {}
    for case, ok, _ in results:
        passed, total = by_cat.get(case["category"], (0, 0))
        by_cat[case["category"]] = (passed + (1 if ok else 0), total + 1)
    lines.append("")
    lines.append("Summary by category:")
    for cat in sorted(by_cat):
        passed, total = by_cat[cat]
        lines.append(f"  {cat}: {passed}/{total}")
    passed_total = sum(1 for _, ok, _ in results if ok)
    lines.append(f"Cases passed: {passed_total}/{len(results)}")
    return lines, (0 if passed_total == len(results) else 1), results


def main():
    parser = argparse.ArgumentParser(description="Golden dataset scorer v1")
    parser.add_argument("--dataset", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "golden_dataset_v1.json"))
    args = parser.parse_args()
    lines, code, _ = run_dataset(args.dataset)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
