"""CONNECT hedge: N threads open tunnels through the proxy at once.

Each thread opens a CONNECT tunnel to an embedded echo server, sends
random bytes both ways, verifies the echo, and closes cleanly. Then the
script audits attempts.db: tunnels opened / succeeded / failed, rows
logged, lost rows, duplicate attempt numbers, InterfaceErrors seen by
the logging wrapper, and created_at order against id.

Self-contained: starts its own echo server and proxy. Local hosts only.

Run:
  python evals/connect_load.py --threads 20
  python evals/connect_load.py --threads 50 --stagger-ms 1000 --hold-open 2
"""
import argparse
import os
import socket
import sqlite3
import sys
import threading
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import db as db_module
import proxy as proxy_module


def _recvall(sock, n):
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("upstream closed mid-echo")
        data += chunk
    return data


def _serve_echo(listener, stop):
    listener.settimeout(0.5)
    while not stop.is_set():
        try:
            conn, _ = listener.accept()
        except socket.timeout:
            continue
        except OSError:
            return  # listener closed during shutdown
        threading.Thread(target=_echo_conn, args=(conn,), daemon=True).start()


def _echo_conn(conn):
    with conn:
        while True:
            data = conn.recv(65536)
            if not data:
                return
            conn.sendall(data)


def _require_free_port(host, port, what):
    # A plain bind (no SO_REUSEADDR) fails if anyone listens here. Never
    # share the port: on Windows a second listener silently steals traffic.
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
    except OSError:
        raise SystemExit(
            f"error: {what} port {port} is already in use; stop the other "
            f"process or pass another port")
    finally:
        probe.close()


def _read_head(sock):
    raw = b""
    while b"\r\n\r\n" not in raw:
        chunk = sock.recv(65536)
        if not chunk:
            raise ConnectionError("proxy closed before CONNECT response")
        raw += chunk
    return raw


def _worker(barrier, results, args, run_id, index, total, echo_port):
    trace = f"trace-load-{run_id}-{index:03d}"
    payload = os.urandom(args.payload_bytes)
    outcome = {"trace": trace, "opened": False, "ok": False, "error": ""}
    try:
        barrier.wait(timeout=30)
        if args.stagger_ms:
            time.sleep(index * (args.stagger_ms / 1000.0) / total)
        sock = socket.create_connection(
            ("127.0.0.1", args.proxy_port), timeout=args.timeout)
        with sock:
            sock.sendall(
                f"CONNECT 127.0.0.1:{echo_port} HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{echo_port}\r\n"
                f"X-Trace-Id: {trace}\r\n\r\n".encode())
            head = _read_head(sock)
            status = int(head.split(b"\r\n", 1)[0].split()[1])
            if status != 200:
                outcome["error"] = f"CONNECT status {status}"
                return
            outcome["opened"] = True
            sock.sendall(payload)
            if _recvall(sock, len(payload)) != payload:
                outcome["error"] = "echo mismatch"
                return
            if args.hold_open:
                time.sleep(args.hold_open)
            outcome["ok"] = True
    except Exception as exc:
        outcome["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        results.append(outcome)


def main():
    parser = argparse.ArgumentParser(description="N-thread CONNECT hedge")
    parser.add_argument("--proxy-port", type=int, default=8888)
    parser.add_argument("--threads", type=int, default=20)
    parser.add_argument("--stagger-ms", type=float, default=0.0)
    parser.add_argument("--hold-open", type=float, default=0.0)
    parser.add_argument("--payload-bytes", type=int, default=4096)
    parser.add_argument("--db", default="load_connect.db")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    run_id = uuid.uuid4().hex[:8]

    if os.path.exists(args.db):
        os.remove(args.db)
    _require_free_port("127.0.0.1", args.proxy_port, "proxy")

    real_log_attempt = db_module.log_attempt
    log_errors = []
    errors_lock = threading.Lock()

    def counting_log_attempt(*args_, **kwargs):
        try:
            return real_log_attempt(*args_, **kwargs)
        except Exception as exc:
            with errors_lock:
                log_errors.append(type(exc).__name__)
            raise

    db_module.log_attempt = counting_log_attempt
    try:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        echo_port = listener.getsockname()[1]
        stop = threading.Event()
        threading.Thread(target=_serve_echo, args=(listener, stop),
                         daemon=True).start()

        proxy = proxy_module.serve("127.0.0.1", args.proxy_port, args.db)
        threading.Thread(target=proxy.serve_forever, daemon=True).start()

        barrier = threading.Barrier(args.threads)
        results = []
        threads = [threading.Thread(target=_worker,
                                    args=(barrier, results, args,
                                          run_id, i, args.threads,
                                          echo_port))
                   for i in range(args.threads)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        alive = [t for t in threads if t.is_alive()]

        proxy.shutdown()
        proxy.server_close()
        proxy.state.conn.close()
        stop.set()
        listener.close()

        opened = sum(1 for r in results if r["opened"])
        succeeded = sum(1 for r in results if r["ok"])
        failed = [r for r in results if not r["ok"]]
        conn = sqlite3.connect(args.db)
        conn.row_factory = sqlite3.Row
        rows = [r for r in conn.execute("SELECT * FROM attempts ORDER BY id")
                if r["trace_id"].startswith(f"trace-load-{run_id}-")]
        conn.close()
        logged_traces = {r["trace_id"] for r in rows}
        opened_traces = {r["trace"] for r in results if r["opened"]}
        lost = sorted(opened_traces - logged_traces)
        attempts_by_trace = {}
        for r in rows:
            attempts_by_trace.setdefault(r["trace_id"], []).append(r["attempt"])
        duplicates = {t: a for t, a in attempts_by_trace.items()
                      if sorted(a) != [1] * len(a) or len(a) != 1}
        stamps = [r["created_at"] for r in rows]
        ordered = stamps == sorted(stamps)

        print(f"run={run_id} threads={args.threads} "
              f"payload={args.payload_bytes}B echo_port={echo_port}")
        print(f"opened={opened} succeeded={succeeded} "
              f"failed={len(failed)} rows={len(rows)}")
        print(f"log_errors={log_errors or 'none'} hung_threads={len(alive)}")
        ok = True

        def check(name, good, detail=""):
            nonlocal ok
            print(f"[{'PASS' if good else 'FAIL'}] {name} {detail}".rstrip())
            if not good:
                ok = False

        check("all tunnels opened", opened == args.threads,
              f"({opened}/{args.threads})")
        check("all tunnels echoed cleanly", succeeded == args.threads,
              f"({succeeded}/{args.threads})")
        for r in failed[:5]:
            print(f"  failed {r['trace']}: {r['error']}")
        check("no lost rows", not lost, f"({lost})" if lost else "")
        check("no duplicate attempts", not duplicates,
              f"({duplicates})" if duplicates else "")
        check("no logging errors", not log_errors,
              f"({log_errors})" if log_errors else "")
        check("created_at ordered with id", ordered)
        check("no hung threads", not alive)
        return 0 if ok else 1
    finally:
        db_module.log_attempt = real_log_attempt


if __name__ == "__main__":
    raise SystemExit(main())
