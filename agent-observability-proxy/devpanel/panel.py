"""Devtool panel, dev only, not the consumer app.

Wireshark-like live view of what Iris sees, plus one Pause button, for
the human running Iris on this machine. Loopback only. Metadata only:
no bodies, no keys, no real hostnames. Human-visible text uses plain
words only: no billable vendor, no priced cost, no attempt_cost, no
trace_id, no dest_host, no hyphenated jargon. Money shows as Money
spent and What you paid. Verdicts read Correct, Incorrect, Unverified,
never failed, never unknown.

Start it (agent-observability-proxy is the working directory):
  .\\.venv\\Scripts\\python.exe devpanel/panel.py --port 8000
Then open http://127.0.0.1:8000/ in a browser.
The panel watches the proxy it starts beside itself on port 8888
(--proxy-port to change it, --db to point at another journal file).
Stop the other dashboard first if it already owns port 8000.

The Pause button calls devpanel.pause_run, a plain human-only
function, in the same local process. The main API stays GET-only:
no control route was added there. This dev-only app is the only place
a click can pause anything, and it only listens on loopback.
"""
from __future__ import annotations

import argparse
import html
import os
import sqlite3
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import api as api_module
import proxy as proxy_module
from devpanel import pause_run as seam_pause_run
from devpanel import states as states_module
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse

BANNER = ("dev only, not the consumer app: every button here acts on "
          "the live proxy on this machine")


def _short(trace_id: str) -> str:
    """Human name for a Run: short, plain, no jargon."""
    return "Run " + (trace_id or "?")[:8]


def _esc(text: object) -> str:
    return html.escape("" if text is None else str(text), quote=True)


def _money(value) -> str:
    return "unknown" if value is None else f"${value:.2f}"


def _option(value: str, selected: bool) -> str:
    picked = " selected" if selected else ""
    shown = value if value else "any"
    return ("<option value=\"" + value + "\"" + picked + ">"
            + shown + "</option>")


def _row_words(row: dict) -> str:
    """One plain-words line for a journal row."""
    if row["outcome"] == "paused":
        return "paused: run stopped, retry needs a fresh Verify."
    if row["outcome"] == "blocked":
        return f"blocked: {row['reason'] or 'not allowed'}."
    if row["outcome"] == "rate_limited":
        return "slowed down by the rate limit."
    if row["outcome"] == "redirected":
        return "redirected: run now goes to its safe destination."
    if row["outcome"] == "stopped":
        return "stopped: all runs stopped, approval needed for a new Run."
    if row["outcome"] == "verified":
        if row["status"] == "success":
            return "verified Correct: read back matched the claim."
        if row["status"] == "failure":
            return "verified Incorrect: read back contradicted the claim."
        return "unverified: read back could not be done."
    if row["outcome"] == "warned":
        return "warned, money spent at 80% of cap."
    if row["status"] == "success":
        return "allowed: run flowed."
    if row["status"] == "unknown":
        return "unverified: nothing checked this yet."
    return "failed: run did not go through."


def _rows_for(trace_id: str) -> list:
    """Every journal row for one Run, oldest first. Read only."""
    conn = sqlite3.connect(api_module.DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(
            "SELECT * FROM attempts WHERE trace_id = ? ORDER BY id",
            (trace_id,))]
    finally:
        conn.close()


def _all_rows() -> list:
    """Every journal row, oldest first. Read only."""
    conn = sqlite3.connect(api_module.DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(
            "SELECT * FROM attempts ORDER BY id")]
    finally:
        conn.close()


app = FastAPI(title="Iris devtool panel (dev only)",
              docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/", response_class=HTMLResponse)
def index(request: Request, run: str = "", dest: str = "",
          verdict: str = "", blocked: str = ""):
    """Live run list with filters. GET only: looking changes nothing."""
    summaries = api_module.list_traces(limit=100)["traces"]
    shown = []
    for summary in summaries:
        trace_id = summary["trace_id"]
        rows = _rows_for(trace_id)
        if not rows:
            continue
        run_verdict = states_module.verdict_for(rows)
        if run and run not in trace_id:
            continue
        if dest and dest not in (summary.get("dest_host") or ""):
            continue
        if verdict and verdict != run_verdict:
            continue
        if blocked and not any(r["outcome"] == "blocked" for r in rows):
            continue
        state = states_module.run_state(rows)
        live, why = states_module.pause_button_live(state)
        shown.append({
            "trace_id": trace_id,
            "label": _short(trace_id),
            "dest": summary.get("dest_host") or "",
            "method": summary.get("method") or "",
            "words": _row_words(dict(summary)),
            "bytes_in": summary.get("bytes_in") or 0,
            "bytes_out": summary.get("bytes_out") or 0,
            "latency": summary.get("latency_seconds") or 0,
            "cost": summary.get("cost"),
            "verdict": run_verdict,
            "state": state,
            "pause_live": live,
            "pause_why": why,
        })
    cards = []
    for item in shown:
        tid = item["trace_id"]
        pause_cell = (
            '<form method="post" action="/runs/' + tid + '/pause">'
            '<button type="submit">Pause</button></form>'
            if item["pause_live"] else _esc(item["pause_why"]))
        cards.append(
            "<tr>"
            f'<td><a href="/runs/{tid}">{_esc(item["label"])}</a></td>'
            f"<td>{_esc(item['dest'])}</td>"
            f"<td>{_esc(item['method'])}</td>"
            f"<td>{_esc(item['words'])}</td>"
            f"<td>{item['bytes_in']} in / {item['bytes_out']} out</td>"
            f"<td>{item['latency']}s</td>"
            f"<td>Money spent {_money(item['cost'])}</td>"
            f"<td>{_esc(item['verdict'])}</td>"
            f"<td>{pause_cell}</td>"
            "</tr>")
    totals = api_module.stats()
    return (
        "<html><head><title>Iris devtool panel, dev only</title></head>"
        "<body>"
        f"<p><strong>{_esc(BANNER)}</strong></p>"
        "<h1>Runs, live</h1>"
        '<form method="get" action="/">'
        f'Run contains: <input name="run" value="{_esc(run)}"> '
        f'Destination contains: <input name="dest" value="{_esc(dest)}"> '
        '<label>Verdict <select name="verdict">'
        + "".join(_option(v, v == verdict)
                  for v in ("", "Correct", "Incorrect", "Unverified"))
        + "</label> "
        f'<label><input type="checkbox" name="blocked" value="1"'
        f'{" checked" if blocked else ""}> blocked only</label> '
        '<button type="submit">Filter</button>'
        "</form>"
        "<table>"
        "<tr><th>Run</th><th>Destination</th><th>Method</th><th>What</th>"
        "<th>Bytes</th><th>Seconds</th><th>Cost</th><th>Verdict</th>"
        "<th>Pause</th></tr>"
        + "".join(cards) +
        "</table>"
        f"<p>What you paid across {totals['total_attempts']} tries: "
        f"{_money(totals['total_cost'])}.</p>"
        "</body></html>")


@app.get("/runs/{trace_id}", response_class=HTMLResponse)
def run_detail(trace_id: str):
    """One Run: every journal row, the plain-words card, next step."""
    rows = _rows_for(trace_id)
    if not rows:
        return HTMLResponse(
            "<html><body><p>Unknown run.</p>"
            '<p><a href="/">Back to runs</a></p></body></html>',
            status_code=404)
    state = states_module.run_state(rows)
    verdict = states_module.verdict_for(rows)
    live, why = states_module.pause_button_live(state)
    lines = []
    for row in rows:
        lines.append(
            "<tr>"
            f"<td>{_esc(row['created_at'])}</td>"
            f"<td>{_esc(row['dest_host'])}</td>"
            f"<td>{_esc(row['method'])}</td>"
            f"<td>{_esc(_row_words(row))}</td>"
            f"<td>{row['bytes_in']} in / {row['bytes_out']} out</td>"
            f"<td>Money spent {_money(api_module.attempt_cost(row))}</td>"
            "</tr>")
    pause_part = (
        f'<form method="post" action="/runs/{_esc(trace_id)}/pause">'
        "<button type=\"submit\">Pause this Run</button></form>"
        "<p>Pressing Pause stops this run unless a human verifies "
        "everything is fine.</p>"
        if live else f"<p>{_esc(why)}</p>")
    return (
        "<html><head><title>Run detail, dev only</title></head><body>"
        f"<p><strong>{_esc(BANNER)}</strong></p>"
        f"<h1>{_esc(_short(trace_id))}</h1>"
        f"<p>Run state: {_esc(state)}. "
        f"Verdict: {_esc(verdict)}.</p>"
        f"<p>Next step: {_esc(states_module.next_step(state, verdict))}</p>"
        f"{pause_part}"
        "<h2>Journal, oldest first</h2>"
        "<table><tr><th>When</th><th>Destination</th><th>Method</th>"
        "<th>What</th><th>Bytes</th><th>Money spent</th></tr>"
        + "".join(lines) +
        "</table>"
        '<p><a href="/">Back to runs</a></p>'
        "</body></html>")


@app.post("/runs/{trace_id}/pause")
def pause_button(trace_id: str, request: Request):
    """The Pause button: calls the plain human-only function, nothing else.

    Dev only, loopback only. This is the one control route in the whole
    panel app, and the main API stays GET-only: no agent can reach it
    through the proxy, and nothing here is reachable off this machine.
    """
    state = getattr(request.app.state, "proxy_state", None)
    if state is None:
        return HTMLResponse(
            "<html><body><p>Panel is watching only: start it beside "
            "a live proxy to pause.</p>"
            '<p><a href="/">Back to runs</a></p></body></html>',
            status_code=503)
    seam_pause_run(state, trace_id, reason="human pause")
    return RedirectResponse(f"/runs/{trace_id}", status_code=303)


def serve_dev(host: str = "127.0.0.1", panel_port: int = 8000,
              proxy_port: int = 8888, db_path=None):
    """Start the watched proxy and the dev panel in one local process.

    Both listen on loopback only. The panel reads the same journal file
    the proxy writes, and the Pause button calls the seam with the same
    live proxy state, so what the panel shows is what Iris enforces.
    """
    import uvicorn

    db_path = db_path or api_module.DB_PATH
    api_module.DB_PATH = db_path
    proxy = proxy_module.serve(host, proxy_port, db_path)
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    app.state.proxy_state = proxy.state
    print(f"iris proxy listening on {host}:{proxy_port} db={db_path}")
    print(f"dev panel at http://{host}:{panel_port}/ "
          f"({BANNER})")
    uvicorn.run(app, host=host, port=panel_port)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--proxy-port", type=int, default=8888)
    parser.add_argument("--db", default=None)
    args = parser.parse_args(argv)
    serve_dev(args.host, args.port, args.proxy_port, args.db)


if __name__ == "__main__":
    main()
