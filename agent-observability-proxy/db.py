"""M1 attempts database: one SQLite row per proxy attempt, metadata only.

Table `attempts` (v0.3 columns plus M1 proxy columns):
  id, trace_id, task_number, attempt, strategy, status,
  latency_seconds, input_tokens, cost_dollars, retry_reason, created_at,
  dest_host, endpoint, method, bytes_in, bytes_out, http_status,
  outcome, reason, bytes_tx, bytes_rx, close_reason, connect_ms,
  duration_ms

bytes_tx counts what the proxy sent toward the destination, bytes_rx
what came back from it (bodies for plain HTTP, relayed bytes for a
CONNECT tunnel; headers are never counted). close_reason says how the
row ended: success, client_eof, upstream_reset, blocked_allowlist,
rate_limited, relay_timeout, or unknown when none of those is known.
connect_ms is the upstream connect time, duration_ms the whole row.

No Authorization headers, API keys, or prompt/response bodies are stored.
Cost/tokens are stored only when the caller supplies them; otherwise 0.
"""

from __future__ import annotations

import datetime
import os
import sqlite3
import threading

_write_lock = threading.Lock()

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    task_number INTEGER NOT NULL,
    attempt INTEGER NOT NULL,
    strategy TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    latency_seconds REAL NOT NULL DEFAULT 0.0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    cost_dollars REAL NOT NULL DEFAULT 0.0,
    retry_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    dest_host TEXT NOT NULL DEFAULT '',
    endpoint TEXT NOT NULL DEFAULT '',
    method TEXT NOT NULL DEFAULT '',
    bytes_in INTEGER NOT NULL DEFAULT 0,
    bytes_out INTEGER NOT NULL DEFAULT 0,
    http_status INTEGER,
    outcome TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    bytes_tx INTEGER NOT NULL DEFAULT 0,
    bytes_rx INTEGER NOT NULL DEFAULT 0,
    close_reason TEXT NOT NULL DEFAULT '',
    connect_ms REAL,
    duration_ms REAL
);
"""


def init_db(path: str) -> sqlite3.Connection:
    """Open (or create) the database at path and ensure the table exists."""
    conn = sqlite3.connect(path, check_same_thread=False)  # proxy logs from worker threads
    conn.execute(CREATE_TABLE_SQL)
    # M4 migration: add outcome/reason to a pre-M4 database in place.
    # Two processes can arrive here together; if a peer wins the race
    # the ALTER fails duplicate-column and the re-check below lets us
    # continue. Anything else is re-raised, never masked.
    existing = {row[1] for row in conn.execute("PRAGMA table_info(attempts)")}
    for name, coltype in (
        ("outcome", "TEXT NOT NULL DEFAULT ''"),
        ("reason", "TEXT NOT NULL DEFAULT ''"),
        ("bytes_tx", "INTEGER NOT NULL DEFAULT 0"),
        ("bytes_rx", "INTEGER NOT NULL DEFAULT 0"),
        ("close_reason", "TEXT NOT NULL DEFAULT ''"),
        ("connect_ms", "REAL"),
        ("duration_ms", "REAL"),
    ):
        if name not in existing:
            try:
                conn.execute(f"ALTER TABLE attempts ADD COLUMN {name} {coltype}")
            except sqlite3.OperationalError:
                cols = {row[1] for row in conn.execute("PRAGMA table_info(attempts)")}
                if name not in cols:
                    raise
    conn.commit()
    return conn


def get_connection(path: str | None = None) -> sqlite3.Connection:
    """Backwards-compatible helper for v0.3-style callers."""
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "attempts.db")
    return init_db(path)


def log_attempt(
    conn: sqlite3.Connection,
    *,
    trace_id: str,
    task_number: int,
    attempt: int,
    status: str,
    latency_seconds: float = 0.0,
    input_tokens: int = 0,
    cost_dollars: float = 0.0,
    retry_reason: str = "",
    strategy: str = "",
    dest_host: str = "",
    endpoint: str = "",
    method: str = "",
    bytes_in: int = 0,
    bytes_out: int = 0,
    http_status: int | None = None,
    created_at: str | None = None,
    outcome: str = "",
    reason: str = "",
    bytes_tx: int = 0,
    bytes_rx: int = 0,
    close_reason: str = "",
    connect_ms: float | None = None,
    duration_ms: float | None = None,
) -> None:
    """Insert one metadata-only attempt row and commit it."""
    with _write_lock:
        if created_at is None:
            created_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        conn.execute(
            """
            INSERT INTO attempts
            (trace_id, task_number, attempt, strategy, status,
             latency_seconds, input_tokens, cost_dollars, retry_reason, created_at,
             dest_host, endpoint, method, bytes_in, bytes_out, http_status,
             outcome, reason, bytes_tx, bytes_rx, close_reason, connect_ms,
             duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trace_id,
                task_number,
                attempt,
                strategy,
                status,
                latency_seconds,
                input_tokens,
                cost_dollars,
                retry_reason,
                created_at,
                dest_host,
                endpoint,
                method,
                bytes_in,
                bytes_out,
                http_status,
                outcome,
                reason,
                bytes_tx,
                bytes_rx,
                close_reason,
                connect_ms,
                duration_ms,
            ),
        )
        conn.commit()


def fetch_totals(conn):
    prev_factory = conn.row_factory
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            """
            SELECT COUNT(*) AS attempts,
                   COUNT(DISTINCT trace_id) AS traces,
                   SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS successes,
                   SUM(CASE WHEN attempt > 1 THEN 1 ELSE 0 END) AS retries,
                   ROUND(AVG(latency_seconds), 4) AS avg_latency_seconds,
                   SUM(bytes_in) AS bytes_in,
                   SUM(bytes_out) AS bytes_out,
                   SUM(input_tokens) AS input_tokens,
                   ROUND(SUM(cost_dollars), 6) AS cost_dollars
            FROM attempts
            """
        ).fetchone()
    finally:
        conn.row_factory = prev_factory


def fetch_report(conn):
    prev_factory = conn.row_factory
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            """
            SELECT dest_host, endpoint, method,
                   COUNT(*) AS attempts,
                   SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS successes,
                   SUM(CASE WHEN attempt > 1 THEN 1 ELSE 0 END) AS retries,
                   ROUND(AVG(latency_seconds), 4) AS avg_latency_seconds,
                   SUM(bytes_in) AS bytes_in,
                   SUM(bytes_out) AS bytes_out
            FROM attempts
            GROUP BY dest_host, endpoint, method
            ORDER BY attempts DESC, dest_host, endpoint
            """
        ).fetchall()
    finally:
        conn.row_factory = prev_factory


def fetch_outcome_counts(conn) -> dict:
    """M4 counts: allowed, blocked, rate_limited, plus other.

    "other" catches NULL, empty, or legacy outcomes from a migrated
    pre-M4 database, so the four counts always add up to total
    attempts instead of silently dropping rows.
    """
    counts = {"allowed": 0, "blocked": 0, "rate_limited": 0, "other": 0}
    for outcome, n in conn.execute(
            "SELECT outcome, COUNT(*) FROM attempts GROUP BY outcome"):
        if outcome in ("allowed", "blocked", "rate_limited"):
            counts[outcome] = n
        else:
            counts["other"] += n
    return counts
