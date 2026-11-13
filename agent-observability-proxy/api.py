"""Read-only dashboard API over the proxy's attempts database.

Reads the same SQLite file the proxy writes (default: attempts.db next
to this file) and exposes trace metadata only: method, endpoint,
bytes in/out, attempt count, outcome, latency. No bodies, no header
values, no API keys are stored in the database, and this API does not
add any. GET only: there are no POST/PUT/DELETE endpoints and nothing
here can start, stop, or reconfigure the proxy.

Run (project folder, port 8000, proxy stays on 8888):
    .venv\\Scripts\\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import os
import sqlite3

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

import db as db_module

DB_PATH = os.environ.get(
    "PROXY_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "attempts.db"),
)

# Columns this API is allowed to expose. Anything else in the table
# (tokens, cost, strategy, retry text) stays out of every response.
TRACE_COLUMNS = (
    "id",
    "trace_id",
    "attempt",
    "status",
    "latency_seconds",
    "created_at",
    "dest_host",
    "endpoint",
    "method",
    "bytes_in",
    "bytes_out",
    "http_status",
    "outcome",
    "reason",
)

app = FastAPI(title="agent-observability read-only API")


@app.middleware("http")
async def _no_store(request, call_next):
    """Never let the browser cache API data or the page itself."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


def _connect() -> sqlite3.Connection | None:
    """Open the database read-only; None when the file is not there yet."""
    if not os.path.exists(DB_PATH):
        return None
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/health")
def health() -> dict:
    return {"ok": True, "db": DB_PATH}


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Agent observability &mdash; local dashboard</title>
<style>
body { font-family: system-ui, sans-serif; max-width: 1100px;
       margin: 2em auto; padding: 0 1em; color: #000; background: #fff;
       font-size: 17px; line-height: 1.5; }
.stats { display: flex; gap: 2em; flex-wrap: wrap; margin: 1em 0; }
.stat b { font-size: 1.6em; display: block; }
.stat small { display: block; font-size: 14px; }
a:focus-visible, button:focus-visible { outline: 3px solid #000; outline-offset: 2px; }
#live { font-weight: bold; }
button { font-size: 16px; padding: 6px 14px; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; }
th, td { border: 1px solid #999; padding: 4px 8px; text-align: left;
         font-size: 14px; }
th { background: #eee; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
#updated { color: #444; font-size: 13px; margin-left: 1em; }
</style>
</head>
<body>
<h1>Agent observability &mdash; local dashboard</h1>
<p>Local proxy only. Metadata only. No bodies, no keys.</p>
<p id="live" role="status">Live &mdash; waiting for the first update&hellip;</p>
<p>Reading database: <code id="dbpath">&hellip;</code></p>
<h2>Stats</h2>
<div class="stats">
<div class="stat">total attempts<b id="s-total">&ndash;</b><small>all tries counted</small></div>
<div class="stat">allowed<b id="s-allowed">&ndash;</b><small>let through</small></div>
<div class="stat">blocked<b id="s-blocked">&ndash;</b><small>stopped by the allowlist</small></div>
<div class="stat">rate limited<b id="s-limited">&ndash;</b><small>slowed down</small></div>
<div class="stat">successes<b id="s-success">&ndash;</b><small>completed</small></div>
<div class="stat">average latency (seconds)<b id="s-lat">&ndash;</b><small>mean wait per try</small></div>
</div>
<button id="refresh" type="button">Refresh now</button>
<h2>Runs (newest first)</h2>
<table aria-label="Runs, newest first">
<thead><tr><th scope="col">Run</th><th scope="col">summary</th><th scope="col">method</th>
<th scope="col">endpoint</th><th scope="col">destination host</th>
<th scope="col">outcome</th><th scope="col">status</th>
<th scope="col">bytes in</th><th scope="col">bytes out</th>
<th scope="col">latency (seconds)</th><th scope="col">attempts</th></tr></thead>
<tbody id="traces"></tbody>
</table>
<h2>Run detail</h2>
<div id="detail"><p>Click a Run to see its attempts.</p></div>
<noscript><p>This dashboard needs JavaScript turned on to load numbers.</p></noscript>
<script>
document.getElementById("live").textContent = "Live — starting first update…";
window.addEventListener("error", function (e) {
  document.getElementById("live").textContent =
    "Live — page error: " + e.message + " (" + e.filename + ":" + e.lineno + ")";
});
window.addEventListener("unhandledrejection", function (e) {
  document.getElementById("live").textContent =
    "Live — update failed: " + ((e.reason && e.reason.message) || e.reason);
});
async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(url + " -> " + r.status);
  return r.json();
}
function td(text, num) {
  const c = document.createElement("td");
  c.textContent = text;
  if (num) c.className = "num";
  return c;
}
const rowsById = new Map();
function makeRunRow(t) {
  const tr = document.createElement("tr");
  const link = document.createElement("a");
  link.href = "#run-" + encodeURIComponent(t.trace_id);
  link.textContent = "Run " + t.trace_id.slice(0, 8);
  link.title = t.trace_id;
  link.setAttribute("aria-label", "Run " + t.trace_id);
  link.dataset.tid = t.trace_id;
  const idCell = document.createElement("td");
  idCell.appendChild(link);
  tr.append(idCell, td(""), td(""), td(""), td(""), td(""), td(""),
            td("", true), td("", true), td("", true), td("", true));
  updateRunRow(tr, t);
  return tr;
}
function updateRunRow(tr, t) {
  const c = tr.children;
  c[1].textContent = runSummary(t);
  c[2].textContent = t.method;
  c[3].textContent = t.endpoint;
  c[4].textContent = t.dest_host;
  c[5].textContent = outcomeWords(t);
  c[6].textContent = t.status;
  c[7].textContent = t.bytes_in;
  c[8].textContent = t.bytes_out;
  c[9].textContent = t.latency_seconds;
  c[10].textContent = t.attempt_count;
}
function outcomeWords(t) {
  if (t.outcome === "blocked") return "blocked by the allowlist";
  if (t.outcome === "rate_limited") return "slowed down by the rate limit";
  if (!t.outcome) return "not recorded";
  if (t.status === "success") return "allowed";
  return "failed";
}
function runSummary(t) {
  return "Tried " + t.method + " " + t.dest_host + t.endpoint +
    " — " + outcomeWords(t) + ".";
}
function setLive(text) {
  document.getElementById("live").textContent = text;
}
async function load() {
  try {
    document.getElementById("dbpath").textContent = (await getJSON("/health")).db;
    const s = await getJSON("/stats");
    document.getElementById("s-total").textContent = s.total_attempts;
    document.getElementById("s-allowed").textContent = s.allowed;
    document.getElementById("s-blocked").textContent = s.blocked;
    document.getElementById("s-limited").textContent = s.rate_limited;
    document.getElementById("s-success").textContent = s.successes;
    document.getElementById("s-lat").textContent = s.avg_latency_seconds;
    const body = document.getElementById("traces");
    const seen = new Set();
    let prev = null;
    for (const t of (await getJSON("/traces?limit=20")).traces) {
      seen.add(t.trace_id);
      let tr = rowsById.get(t.trace_id);
      if (!tr) {
        tr = makeRunRow(t);
        rowsById.set(t.trace_id, tr);
      } else {
        updateRunRow(tr, t);
      }
      body.insertBefore(tr, prev ? prev.nextSibling : body.firstChild);
      prev = tr;
    }
    for (const [tid, tr] of rowsById) {
      if (!seen.has(tid)) {
        tr.remove();
        rowsById.delete(tid);
      }
    }
    setLive("Live — updated " + new Date().toLocaleTimeString());
  } catch (err) {
    setLive("Live — update failed, will retry. (" + err.message + ")");
  }
}
async function showTrace(tid) {
  const box = document.getElementById("detail");
  box.replaceChildren();
  const h = document.createElement("h3");
  h.textContent = "Run " + tid;
  const tab = document.createElement("table");
  tab.setAttribute("aria-label", "Attempts in run " + tid);
  tab.innerHTML = '<thead><tr><th scope="col">attempt</th>' +
    '<th scope="col">time</th><th scope="col">method</th>' +
    '<th scope="col">endpoint</th><th scope="col">destination host</th>' +
    '<th scope="col">outcome</th><th scope="col">status</th>' +
    '<th scope="col">http</th><th scope="col">bytes in</th>' +
    '<th scope="col">bytes out</th>' +
    '<th scope="col">latency (seconds)</th>' +
    '<th scope="col">reason</th></tr></thead>';
  const tb = document.createElement("tbody");
  for (const a of (await getJSON("/traces/" + encodeURIComponent(tid))).attempts) {
    const tr = document.createElement("tr");
    tr.append(td(a.attempt, true), td(a.created_at), td(a.method),
              td(a.endpoint), td(a.dest_host), td(a.outcome),
              td(a.status), td(a.http_status, true), td(a.bytes_in, true),
              td(a.bytes_out, true), td(a.latency_seconds, true),
              td(a.reason));
    tb.appendChild(tr);
  }
  tab.appendChild(tb);
  box.append(h, tab);
}
document.getElementById("traces").addEventListener("click", (e) => {
  const link = e.target.closest("a[data-tid]");
  if (link) { e.preventDefault(); showTrace(link.dataset.tid); }
});
document.getElementById("refresh").addEventListener("click", load);
setInterval(load, 5000);
load();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return DASHBOARD_HTML


@app.get("/traces")
def list_traces(limit: int = 20) -> dict:
    """Newest traces first; one summary row per trace_id."""
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="limit must be 1..100")
    conn = _connect()
    if conn is None:
        return {"traces": []}
    try:
        cols = ", ".join(f"a.{c}" for c in TRACE_COLUMNS)
        rows = conn.execute(
            f"""
            SELECT {cols}, t.attempt_count FROM attempts a
            JOIN (
                SELECT trace_id, MAX(id) AS latest_id,
                       COUNT(*) AS attempt_count
                FROM attempts
                GROUP BY trace_id
            ) t ON t.latest_id = a.id
            ORDER BY a.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return {"traces": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.get("/traces/{trace_id}")
def get_trace(trace_id: str) -> dict:
    """Every attempt row for one trace, oldest first; 404 when unknown."""
    conn = _connect()
    if conn is None:
        raise HTTPException(status_code=404, detail="trace not found")
    try:
        cols = ", ".join(TRACE_COLUMNS)
        rows = conn.execute(
            f"SELECT {cols} FROM attempts WHERE trace_id = ? ORDER BY id",
            (trace_id,),
        ).fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail="trace not found")
        return {"trace_id": trace_id, "attempts": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.get("/stats")
def stats() -> dict:
    """Counts only: totals by outcome, successes, average latency."""
    conn = _connect()
    if conn is None:
        return {
            "total_attempts": 0,
            "allowed": 0,
            "blocked": 0,
            "rate_limited": 0,
            "successes": 0,
            "avg_latency_seconds": 0.0,
        }
    try:
        total = conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
        counts = db_module.fetch_outcome_counts(conn)
        row = conn.execute(
            """
            SELECT COUNT(CASE WHEN status = 'success' THEN 1 END),
                   ROUND(AVG(latency_seconds), 4)
            FROM attempts
            """
        ).fetchone()
        return {
            "total_attempts": total,
            "allowed": counts["allowed"],
            "blocked": counts["blocked"],
            "rate_limited": counts["rate_limited"],
            "successes": row[0] or 0,
            "avg_latency_seconds": row[1] or 0.0,
        }
    finally:
        conn.close()
