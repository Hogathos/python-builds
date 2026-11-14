"""Visualizer v2: M1 attempts database -> trace-diagram.md for GitHub.

Reads demo traces only (local test server, loopback destination) from the
SQLite `attempts` table and writes one Markdown file with headline numbers
in plain text plus a Mermaid flowchart GitHub renders natively.

v2 fixes Malm's v1 nits: traces are sorted by trace ID so Trace A is
always first (not C, B, A); long traces collapse middle retries into one
summary node; endpoints show path plus argument count only, and POST
attempts show method, endpoint, bytes, and argument count only — never
argument values or bodies.

Safety: only an allowlist of metadata columns is ever read. Authorization
headers, API keys, argument values, and prompt/response bodies are never
queried, logged, nor written to the output. Non-loopback (real) traffic
is excluded.

Run:
  python visualizer.py --db attempts.db --output trace-diagram.md
  python visualizer.py --db attempts.db --output trace-diagram.md --seed-demo
"""
from __future__ import annotations

import argparse
import sqlite3
import string
from pathlib import Path

import db as db_module

# Only these columns are read. No headers, keys, values, or bodies exist here.
SAFE_COLUMNS = (
    "id, trace_id, task_number, attempt, status, latency_seconds, "
    "input_tokens, cost_dollars, retry_reason, created_at, "
    "endpoint, method, http_status"
)

BYTES_COLUMNS = "bytes_in, bytes_out"

MAX_DETAIL_STEPS = 5  # longer traces collapse middle retries

DEMO_DEST_PREFIXES = ("127.0.0.1", "localhost", "::1")


def is_demo_row(row: sqlite3.Row) -> bool:
    """Demo traffic only: destination must be the local test server."""
    keys = row.keys()
    dest = (row["dest_host"] if "dest_host" in keys else "") or ""
    if not dest:
        # Pre-extension v0.3 rows carry no destination; only trust them
        # when the trace is explicitly a demo trace.
        return str(row["trace_id"]).startswith("demo-")
    return dest.startswith(DEMO_DEST_PREFIXES)


def fetch_demo_attempts(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            f"SELECT {SAFE_COLUMNS}, dest_host, {BYTES_COLUMNS} FROM attempts ORDER BY id"
        ).fetchall()
    except sqlite3.OperationalError:
        try:
            rows = conn.execute(
                f"SELECT {SAFE_COLUMNS}, dest_host, 0 AS bytes_in, 0 AS bytes_out "
                "FROM attempts ORDER BY id"
            ).fetchall()
        except sqlite3.OperationalError:
            rows = conn.execute(
                f"SELECT {SAFE_COLUMNS}, '' AS dest_host, 0 AS bytes_in, 0 AS bytes_out "
                "FROM attempts ORDER BY id"
            ).fetchall()
    return [r for r in rows if is_demo_row(r)]


def trace_label(index: int) -> str:
    """0 -> A, 1 -> B, ..., 25 -> Z, 26 -> AA (trace_id sort order)."""
    label = ""
    n = index
    while True:
        label = string.ascii_uppercase[n % 26] + label
        n = n // 26 - 1
        if n < 0:
            return label


def group_traces(rows: list[sqlite3.Row]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for row in rows:
        trace = by_id.get(row["trace_id"])
        if trace is None:
            trace = {"trace_id": row["trace_id"], "label": "", "steps": []}
            by_id[row["trace_id"]] = trace
        trace["steps"].append(row)
    traces = sorted(by_id.values(), key=lambda t: t["trace_id"])
    for i, trace in enumerate(traces):
        trace["label"] = trace_label(i)
        trace["steps"].sort(key=lambda r: (r["attempt"], r["id"]))
    return traces


def trace_verdict(trace: dict) -> str:
    steps = trace["steps"]
    succeeded = steps[-1]["status"] == "success"
    if steps[-1]["status"] == "unknown":
        return "UNKNOWN OUTCOME"
    if succeeded and len(steps) == 1:
        return "CLEAN SUCCESS"
    if succeeded:
        return "RETRIED THEN SUCCEEDED"
    if len(steps) > 1:
        return "WASTED - NEVER SUCCEEDED"
    return "FAILED - NO RETRY"


def headline(rows: list[sqlite3.Row], traces: list[dict]) -> dict:
    total_attempts = len(rows)
    total_tasks = len(traces)
    successful_tasks = sum(
        1 for t in traces if t["steps"][-1]["status"] == "success")
    total_retries = sum(1 for r in rows if r["attempt"] > 1)
    total_cost = sum(float(r["cost_dollars"] or 0.0) for r in rows)
    return {
        "total_attempts": total_attempts,
        "total_tasks": total_tasks,
        "successful_tasks": successful_tasks,
        "success_rate": (100.0 * successful_tasks / total_tasks) if total_tasks else 0.0,
        "total_retries": total_retries,
        "total_cost": total_cost,
        "cost_per_success": (total_cost / successful_tasks) if successful_tasks else 0.0,
    }


def _clean(text: object) -> str:
    """Make a DB value safe for a quoted Mermaid label / Markdown cell."""
    out = str(text if text is not None else "")
    for bad in ('"', "[", "]", "(", ")", "{", "}", "|", "<", ">", "#", ";", "\n"):
        out = out.replace(bad, " ")
    return " ".join(out.split())


def _split_endpoint(endpoint: object) -> tuple[str, int]:
    """Split endpoint into (path, arg_count), dropping query values.

    Only the path and the number of query arguments are ever shown.
    Argument names and values are never returned.
    """
    text = str(endpoint or "/")
    text = text.split("#", 1)[0]
    if "?" not in text:
        return (text or "/", 0)
    path, query = text.split("?", 1)
    args = [p for p in query.split("&") if p.strip()]
    return ((path or "/"), len(args))


def _step_label(row: sqlite3.Row) -> str:
    ok = row["status"] == "success"
    unknown = row["status"] == "unknown"
    mark = "SUCCESS" if ok else ("UNKNOWN" if unknown else "FAILED")
    icon = "✅" if ok else ("❓" if unknown else "❌")
    retry = " - RETRY" if row["attempt"] > 1 else ""
    path, arg_count = _split_endpoint(row["endpoint"] or "/")
    path = _clean(path)
    # A CONNECT row is one opaque tunnel, never one request.
    method = ("CONNECT tunnel" if (row["method"] or "") == "CONNECT"
              else _clean(row["method"] or ""))
    args = f" ({arg_count} args)" if arg_count else ""
    http = f" - HTTP {row['http_status']}" if row["http_status"] is not None else ""
    latency = float(row["latency_seconds"] or 0.0)
    cost = float(row["cost_dollars"] or 0.0)
    keys = row.keys()
    bytes_in = int(row["bytes_in"] or 0) if "bytes_in" in keys else 0
    bytes_out = int(row["bytes_out"] or 0) if "bytes_out" in keys else 0
    byte_part = f" - {bytes_in}B in / {bytes_out}B out"
    return (f"{icon} Attempt {int(row['attempt'])}{retry}: {mark}<br/>"
            f"{method} {path}{args}{http}<br/>"
            f"cost ${cost:.4f} - latency {latency:.2f}s{byte_part}")


def _collapsed_label(collapsed: list) -> tuple[str, str]:
    """Return (label, css_class) for a collapsed retry range."""
    count = len(collapsed)
    cost = sum(float(r["cost_dollars"] or 0.0) for r in collapsed)
    latency = sum(float(r["latency_seconds"] or 0.0) for r in collapsed)
    all_failed = all(r["status"] != "success" for r in collapsed)
    all_unknown = all(r["status"] == "unknown" for r in collapsed)
    status = ("outcome unknown" if all_unknown
              else "all FAILED" if all_failed else "mixed")
    label = (f"↻ {count} collapsed retries - {status}<br/>"
             f"cost ${cost:.4f} - latency {latency:.2f}s")
    cls = ("unknown" if all_unknown
           else "failure" if all_failed else "success")
    return (label, cls)


def _append_step_node(lines: list[str], prev: str, node: str, row) -> str:
    lines.append(f'        {node}["{_step_label(row)}"]')
    if row["attempt"] > 1:
        lines.append(f"        {prev} -->|retry| {node}")
    else:
        lines.append(f"        {prev} --> {node}")
    status = row["status"]
    cls = ("success" if status == "success"
           else "unknown" if status == "unknown" else "failure")
    lines.append(f"        class {node} {cls}")
    return node


def build_mermaid(traces: list[dict]) -> str:
    lines = ["flowchart TD"]
    for trace in traces:
        tag = trace["label"]
        verdict = trace_verdict(trace)
        lines.append(f'    subgraph T{tag}["Trace {trace["label"]} - {verdict}"]')
        lines.append(f'        S{tag}(["Start"])')
        prev = f"S{tag}"
        steps = trace["steps"]
        if len(steps) > MAX_DETAIL_STEPS:
            for i, row in enumerate(steps[:2]):
                prev = _append_step_node(lines, prev, f"T{tag}S{i + 1}", row)
            collapsed = steps[2:-1]
            coll_label, coll_class = _collapsed_label(collapsed)
            coll_node = f"T{tag}C"
            lines.append(f'        {coll_node}["{coll_label}"]')
            lines.append(f"        {prev} -->|retry| {coll_node}")
            lines.append(f"        class {coll_node} {coll_class}")
            prev = coll_node
            prev = _append_step_node(lines, prev, f"T{tag}S{len(steps)}", steps[-1])
        else:
            for i, row in enumerate(steps):
                prev = _append_step_node(lines, prev, f"T{tag}S{i + 1}", row)
        end = f"E{tag}"
        end_text = ("Succeeded" if verdict in
                    ("CLEAN SUCCESS", "RETRIED THEN SUCCEEDED")
                    else "Never succeeded - retries wasted")
        lines.append(f'        {end}(["{end_text}"])')
        lines.append(f"        {prev} --> {end}")
        lines.append("    end")
    lines += [
        "    classDef success fill:#1a7f37,color:#ffffff,stroke:#116329,stroke-width:2px",
        "    classDef failure fill:#cf222e,color:#ffffff,stroke:#82071e,stroke-width:2px",
        "    classDef unknown fill:#6e7781,color:#ffffff,stroke:#424a53,stroke-width:2px",
    ]
    return "\n".join(lines)


def render_markdown(rows: list[sqlite3.Row], traces: list[dict]) -> str:
    h = headline(rows, traces)
    out = [
        "# Trace diagram - M1 demo traces",
        "",
        "Generated by `visualizer.py` (version 2) from the M1 attempts "
        "database, demo traffic only (local HTTP test server on loopback). "
        "Metadata only: no secrets, argument values, or request/response "
        "bodies are included.",
        "",
        "## Headline numbers",
        "",
        f"- Total attempts: {h['total_attempts']}",
        f"- Total tasks (traces): {h['total_tasks']}",
        f"- Successful tasks: {h['successful_tasks']}",
        f"- Success rate: {h['success_rate']:.1f}%",
        f"- Total retries: {h['total_retries']}",
        f"- Total cost: ${h['total_cost']:.4f}",
        f"- Cost per success: ${h['cost_per_success']:.4f}",
        "",
        "A task (trace) counts as successful only when its final attempt "
        "succeeds. A retry is any attempt numbered 2 or higher on the "
        "same trace.",
        "",
        "## How to read the diagram",
        "",
        "- Each box group is one trace (one task), labelled Trace A, "
        "Trace B, Trace C, ... sorted by trace ID so Trace A is always first.",
        "- Each box inside a group is one attempt, in order. Follow the "
        "arrows from Start to the finish flag.",
        "- Green SUCCESS = the attempt succeeded. Red FAILED = it failed.",
        "- An arrow marked `retry` plus a repeated attempt box means the "
        "same task was tried again. More boxes = more retries spent.",
        "- Long traces (more than 5 attempts) collapse middle retries "
        "into one summary box to save space; the verdict table still "
        "shows true attempt counts.",
        "- Every attempt box shows method, endpoint path, HTTP status, "
        "cost, latency, and bytes in/out. Query arguments are counted "
        "but never shown; POST bodies are never shown.",
        "- The finish flag states the verdict: clean success (one try), "
        "retried then succeeded, or wasted (retries spent, never succeeded).",
        "",
        "## Per-trace verdicts",
        "",
        "| Trace | Attempts | Retries | Final result | Verdict |",
        "| --- | ---: | ---: | --- | --- |",
    ]
    for trace in traces:
        steps = trace["steps"]
        final = steps[-1]["status"]
        if final not in ("success", "unknown"):
            final = "failure"
        out.append(
            f"| Trace {trace['label']} | {len(steps)} | "
            f"{sum(1 for s in steps if s['attempt'] > 1)} | "
            f"{final} | {trace_verdict(trace)} |")
    out += ["", "## Diagram", "", "```mermaid", build_mermaid(traces), "```", ""]
    return "\n".join(out)


def seed_demo(conn: sqlite3.Connection) -> None:
    """Insert the deterministic M1 demo traces (local test server only).

    Trace A: fails, retries, succeeds. Trace B: succeeds first try.
    Trace C: fails, retries twice, never succeeds (wasted retries).
    Existing demo rows are left untouched; seeding is skipped if any
    demo-trace-* rows already exist.
    """
    existing = conn.execute(
        "SELECT COUNT(*) FROM attempts WHERE trace_id LIKE 'demo-trace-%'"
    ).fetchone()[0]
    if existing:
        return
    demo = [
        # trace_id, task, attempt, status, latency, cost, http, endpoint
        ("demo-trace-a", 1, 1, "failure", 0.42, 0.0020, 500, "/fail"),
        ("demo-trace-a", 1, 2, "success", 0.31, 0.0020, 200, "/echo"),
        ("demo-trace-b", 2, 1, "success", 0.18, 0.0020, 200, "/echo"),
        ("demo-trace-c", 3, 1, "failure", 0.40, 0.0020, 500, "/fail"),
        ("demo-trace-c", 3, 2, "failure", 0.39, 0.0020, 500, "/fail"),
        ("demo-trace-c", 3, 3, "failure", 0.41, 0.0020, 500, "/fail"),
    ]
    for i, (tid, task, attempt, status, latency, cost, http, endpoint) in enumerate(demo):
        db_module.log_attempt(
            conn, trace_id=tid, task_number=task, attempt=attempt,
            status=status, latency_seconds=latency, input_tokens=0,
            cost_dollars=cost, retry_reason="retry" if attempt > 1 else "",
            dest_host="127.0.0.1:18080",
            endpoint=endpoint,
            method="GET", http_status=http,
            created_at=f"2026-01-01T00:00:0{i}+00:00")


def main() -> int:
    parser = argparse.ArgumentParser(description="Visualizer v2: attempts.db -> trace-diagram.md")
    parser.add_argument("--db", default="attempts.db")
    parser.add_argument("--output", default="trace-diagram.md")
    parser.add_argument("--seed-demo", action="store_true",
                        help="insert demo traces A/B/C if none exist yet")
    args = parser.parse_args()

    if not Path(args.db).exists() and not args.seed_demo:
        parser.error(f"database not found: {args.db} "
                     "(run M1 demo traffic first, or pass --seed-demo)")
    conn = db_module.init_db(args.db)
    try:
        if args.seed_demo:
            seed_demo(conn)
        rows = fetch_demo_attempts(conn)
    finally:
        conn.close()
    if not rows:
        parser.error("no demo attempts found (loopback / local test "
                     "server traces only); nothing to visualize")
    traces = group_traces(rows)
    markdown = render_markdown(rows, traces)
    Path(args.output).write_text(markdown, encoding="utf-8")
    h = headline(rows, traces)
    print(f"wrote {args.output}: attempts={h['total_attempts']} "
          f"tasks={h['total_tasks']} successes={h['successful_tasks']} "
          f"retries={h['total_retries']} cost=${h['total_cost']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
