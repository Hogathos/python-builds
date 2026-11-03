"""Layer 2 trajectory checks: assert the execution path, not just final outcomes.

Re-runs the local loopback golden dataset scenarios against the local proxy,
verifying that the path taken by the proxy and agents was sound:
- M3 two-agent trace: exactly 2 rows, 1 trace_id, 1 task, A leg (/task)
  then B leg (/echo), no extra calls, no duplicate trace IDs.
- M4 rate limit: allowed up to the limit (200), then rate_limited (429),
  then succeeds again after a pause (200) — no blocked calls counted as allowed.
- M1 logging: supplied trace_id preserved exactly across client, upstream,
  and DB; generated trace_id returned when none supplied.
- Secrets: no request/response bodies, no keys, in any row or SQLite dump, ever.

Run: python evals/trajectory_checks.py --dataset evals/golden_dataset_v1.json
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

# Ensure proxy root and evals folder are importable
evals_dir = os.path.dirname(os.path.abspath(__file__))
proxy_dir = os.path.abspath(os.path.join(evals_dir, ".."))
if proxy_dir not in sys.path:
    sys.path.insert(0, proxy_dir)
if evals_dir not in sys.path:
    sys.path.insert(0, evals_dir)

import scorer


def check_trajectory(case: dict, env: scorer.Env, actual: dict) -> list[str]:
    """Assert the execution trajectory/path for a scenario."""
    case_id = case["id"]
    exp = case["expected"]
    sc = case["scenario"]
    fails = []
    rows = actual["rows"]

    def need(cond: bool, msg: str):
        if not cond:
            fails.append(msg)

    # Base: verify HTTP status if expected
    if "http_status" in exp and actual.get("status") is not None:
        need(actual["status"] == exp["http_status"],
             f"http_status {actual['status']} != {exp['http_status']}")

    # 1. M3 two-agent trace: A leg (/task) THEN B leg (/echo), 1 trace, 1 task
    if case_id == "m3-two-agent-trace":
        expected_rows = exp.get("rows", 2)
        need(len(rows) == expected_rows,
             f"trajectory row count {len(rows)} != expected {expected_rows}")

        distinct_traces = {r["trace_id"] for r in rows}
        need(len(distinct_traces) == exp.get("distinct_trace_ids", 1),
             f"distinct trace_ids {len(distinct_traces)} != expected {exp.get('distinct_trace_ids', 1)}")
        if sc.get("trace_id"):
            need(distinct_traces == {sc["trace_id"]},
                 f"trace_id {distinct_traces} != expected {sc['trace_id']}")

        distinct_tasks = {r["task_number"] for r in rows}
        need(len(distinct_tasks) == exp.get("distinct_task_numbers", 1),
             f"distinct task_numbers {len(distinct_tasks)} != expected {exp.get('distinct_task_numbers', 1)}")

        legs = exp.get("legs", {"a_endpoint": "/task", "b_endpoint": "/echo"})
        a_endpoint = legs.get("a_endpoint", "/task")
        b_endpoint = legs.get("b_endpoint", "/echo")
        if len(rows) >= 2:
            # In synchronous delegation: Leg A (/task) initiates first and encloses Leg B (/echo).
            # Downstream Leg B completes and logs first (row 0),
            # then enclosing parent Leg A completes and logs second (row 1).
            downstream_leg = rows[0]
            initiating_leg = rows[1]
            need(initiating_leg["endpoint"] == a_endpoint,
                 f"initiating Leg A endpoint {initiating_leg['endpoint']} != expected {a_endpoint}")
            need(downstream_leg["endpoint"] == b_endpoint,
                 f"downstream Leg B endpoint {downstream_leg['endpoint']} != expected {b_endpoint}")
            need(initiating_leg["latency_seconds"] >= downstream_leg["latency_seconds"],
                 "initiating Leg A latency must encompass downstream Leg B latency")
            need(initiating_leg["id"] > downstream_leg["id"],
                 "downstream Leg B must complete before enclosing Leg A")
        else:
            need(False, f"insufficient rows ({len(rows)}) to verify A-then-B trajectory")

    # 2. M4 rate limit burst: progression allowed -> rate_limited -> recovery
    elif case_id == "m4-rate-limit-burst":
        expected_statuses = exp.get("statuses", [200, 200, 200, 200, 200, 429, 429, 200])
        actual_statuses = actual.get("statuses", [])
        need(actual_statuses == expected_statuses,
             f"status sequence {actual_statuses} != expected {expected_statuses}")

        limit = sc.get("rate_limit", 5)
        for i in range(min(limit, len(rows))):
            need(rows[i]["outcome"] == "allowed" and rows[i]["http_status"] == 200,
                 f"call {i} should be allowed up to limit, got {rows[i]['outcome']} ({rows[i]['http_status']})")

        burst_count = sc.get("burst_count", 7)
        for i in range(limit, min(burst_count, len(rows))):
            need(rows[i]["outcome"] == "rate_limited" and rows[i]["http_status"] == 429,
                 f"call {i} should be rate_limited over limit, got {rows[i]['outcome']} ({rows[i]['http_status']})")
            need(rows[i]["reason"] == "rate_limited",
                 f"call {i} reason {rows[i]['reason']} != 'rate_limited'")

        if sc.get("recovery_call") and len(rows) > burst_count:
            recovery_row = rows[-1]
            need(recovery_row["outcome"] == "allowed" and recovery_row["http_status"] == 200,
                 f"recovery call should succeed after pause, got {recovery_row['outcome']} ({recovery_row['http_status']})")

        need(all(r["outcome"] != "blocked" for r in rows),
             "found blocked call in rate limit scenario (no blocked calls allowed)")

        conn = sqlite3.connect(env.db_path)
        try:
            counts = scorer.db_module.fetch_outcome_counts(conn)
        finally:
            conn.close()
        for k, v in exp.get("outcome_counts", {}).items():
            need(counts.get(k, 0) == v, f"outcome count {k}: {counts.get(k, 0)} != {v}")

    # 3. M1 logging: supplied trace preserved
    elif case_id == "m1-echo-supplied-trace":
        expected_trace = sc.get("trace_id", "trace-golden-m1")
        need(len(rows) == exp.get("rows", 1), f"expected {exp.get('rows', 1)} row, got {len(rows)}")
        need(actual.get("response_trace") == expected_trace,
             f"response header trace {actual.get('response_trace')} != {expected_trace}")
        need(all(r["trace_id"] == expected_trace for r in rows),
             f"logged trace_id != supplied trace {expected_trace}")
        need(all(r["outcome"] == "allowed" for r in rows), "row outcome != 'allowed'")
        need(all(r["bytes_out"] >= exp.get("bytes_out_min", 1) for r in rows), "bytes_out below minimum")

    # 4. M1 logging: generated trace returned and logged
    elif case_id == "m1-echo-generated-trace":
        gen_trace = actual.get("response_trace")
        need(bool(gen_trace), "no generated trace returned in response header")
        need(len(rows) == exp.get("rows", 1), f"expected {exp.get('rows', 1)} row, got {len(rows)}")
        need(all(r["trace_id"] == gen_trace for r in rows),
             f"logged trace_id does not match returned generated trace {gen_trace}")
        need(all(r["outcome"] == "allowed" for r in rows), "row outcome != 'allowed'")

    # 5. Secrets: never logged in any column, body, or SQLite dump
    elif case_id == "secrets-never-logged":
        secrets = actual.get("secrets", [])
        dump = env.dump()
        for secret in secrets:
            need(secret not in dump, "secret appears in SQLite dump")
        for r in rows:
            for col in r.keys():
                val = str(r[col])
                for secret in secrets:
                    need(secret not in val, f"secret appears in column {col}")

    # Remaining baseline scenarios
    else:
        if "rows" in exp:
            relevant = actual.get("relevant_rows", rows)
            need(len(relevant) == exp["rows"], f"rows {len(relevant)} != {exp['rows']}")
        if "outcome" in exp:
            need(all(r["outcome"] == exp["outcome"] for r in rows),
                 f"outcome != {exp['outcome']}")
        if exp.get("zero_forwarded_bytes"):
            need(all(r["bytes_in"] == 0 and r["bytes_out"] == 0 for r in rows),
                 "blocked/failed calls must have zero forwarded bytes")
        if exp.get("echo_matches"):
            need(actual.get("echo_ok") is True, "tunnel echo did not match")
        if "outcome_counts" in exp:
            conn = sqlite3.connect(env.db_path)
            try:
                counts = scorer.db_module.fetch_outcome_counts(conn)
            finally:
                conn.close()
            for k, v in exp["outcome_counts"].items():
                need(counts.get(k, 0) == v, f"outcome count {k}: {counts.get(k, 0)} != {v}")

    return fails


def run_trajectory_dataset(dataset_path: str):
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
        env = scorer.Env(**kwargs)
        try:
            actual = scorer.replay(case, env)
            fails = check_trajectory(case, env, actual)
            if case["expected"].get("secrets_absent_from_output"):
                joined = "\n".join(lines)
                for secret in actual.get("secrets", []):
                    if secret in joined:
                        fails.append("a secret value appears in output")
        except Exception as exc:
            fails = [f"replay error: {type(exc).__name__}"]
        finally:
            env.close()
        ok = not fails
        results.append((case, ok, fails))
        lines.append(f"[{'PASS' if ok else 'FAIL'}] {case['id']} "
                     f"(trajectory: {case['category']})"
                     + ("" if ok else f" -- {'; '.join(fails)}"))

    by_cat = {}
    for case, ok, _ in results:
        passed, total = by_cat.get(case["category"], (0, 0))
        by_cat[case["category"]] = (passed + (1 if ok else 0), total + 1)
    lines.append("")
    lines.append("Summary by category (trajectory checks):")
    for cat in sorted(by_cat):
        passed, total = by_cat[cat]
        lines.append(f"  {cat}: {passed}/{total}")
    passed_total = sum(1 for _, ok, _ in results if ok)
    lines.append(f"Trajectory checks passed: {passed_total}/{len(results)}")
    return lines, (0 if passed_total == len(results) else 1), results


def main():
    parser = argparse.ArgumentParser(description="Layer 2 trajectory checks v1")
    parser.add_argument("--dataset", default=os.path.join(evals_dir, "golden_dataset_v1.json"))
    args = parser.parse_args()
    lines, code, _ = run_trajectory_dataset(args.dataset)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
