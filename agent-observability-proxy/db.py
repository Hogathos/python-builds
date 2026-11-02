"""M1 attempts database: one SQLite row per proxy attempt, metadata only.

Table `attempts` (v0.3 columns plus M1 proxy columns):
  id, trace_id, task_number, attempt, strategy, status,
  latency_seconds, input_tokens, cost_dollars, retry_reason, created_at,
  dest_host, endpoint, method, bytes_in, bytes_out, http_status

No Authorization headers, API keys, or prompt/response bodies are stored.
Cost/tokens are stored only when the caller supplies them; otherwise 0.
"""

from __future__ import annotations

import datetime
import os
import sqlite3

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
    http_status INTEGER
);
"""


def init_db(path: str) -> sqlite3.Connection:
    """Open (or create) the database at path and ensure the table exists."""
    conn = sqlite3.connect(path, check_same_thread=False)  # proxy logs from worker threads
    conn.execute(CREATE_TABLE_SQL)
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
) -> None:
    """Insert one metadata-only attempt row and commit it."""
    if created_at is None:
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO attempts
        (trace_id, task_number, attempt, strategy, status,
         latency_seconds, input_tokens, cost_dollars, retry_reason, created_at,
         dest_host, endpoint, method, bytes_in, bytes_out, http_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        ),
    )
    conn.commit()
