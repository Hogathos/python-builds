# Architecture

How the proxy works: milestones, trace propagation, policy, and schema.
For commands, see [running](running.md). Status: M4 + visualizer v2 +
T1–T9 fixes, suite 35/35.

## Milestones

M1 is a plain-HTTP forwarding proxy to a local test server with
metadata-only SQLite logging. M2 adds CONNECT tunnelling: the proxy
accepts `CONNECT host:port`, opens a raw TCP tunnel, and relays bytes
both ways so HTTPS traffic can pass through. The tunnel is never
decrypted (no TLS interception, no MITM), and only metadata is logged
per tunnel: destination host:port, method CONNECT, success/failure,
latency, bytes in/out, and the trace ID (carried on the CONNECT
request, or generated and returned in the `X-Trace-Id` response
header). Payload content, headers, and keys are never logged. A tunnel
silent for 30 s is closed and logged as a failure row.

M3 adds the two-agent trace demo: Agent A calls Agent B through the
proxy, and Agent B calls the upstream test server through the proxy
again, with one `X-Trace-Id` carried across both legs. If A sends no
trace ID, the proxy generates one on the first leg, returns it, and
that same ID is forwarded to B and carried on B's downstream call.
Every attempt from both legs is logged under that one trace_id, with
dest_host / endpoint distinguishing the A leg (Agent B's /task) from
the B leg (upstream /echo).

M4 adds the allowlist and rate limit. Only destinations on the
configurable allowlist are forwarded (default local test hosts
`127.0.0.1`, `localhost`, `::1`; change with `--allowlist` or
`serve(..., allowlist=...)`). A bare host matches any port; a
`host:port` entry matches only that exact port. A non-allowlisted
destination is blocked at the proxy and never forwarded: HTTP gets
403, a CONNECT tunnel is never opened, and the attempt is logged
`outcome=blocked`, `reason=not_allowlisted`. More than the configured
rate limit (`--rate-limit`, default 100 per `--rate-window` 10s, per
destination) gets 429 and is logged `outcome=rate_limited`,
`reason=rate_limited`; after the window passes, requests pass again.
Forwarded attempts log `outcome=allowed`. `report.py` prints allowed /
blocked / rate_limited counts next to the headline metrics.

## Trace IDs and attempt numbers

An incoming `X-Trace-Id` is forwarded unchanged; otherwise the proxy
generates one, adds it upstream, and returns it in the response.
Repeats of the same trace + endpoint + method inside 10 s are logged
as attempt 2, 3, ... with `retry_reason='retry'`. Requests the proxy
refuses (blocked, rate-limited, malformed headers) log a counted but
never consumed attempt number, so they never shift later numbering.
Each trace keeps one task number: the first claim wins, duplicates
across traces fall back to auto-assignment, and explicit numbers push
the auto counter past themselves.

Malformed requests get a 400 plus an audit row
(`reason=malformed_header`), never a dropped connection. The proxy's
own control headers (`X-Task-Number`, `X-Strategy`) are consumed
locally and stripped before forwarding; only `X-Trace-Id` rides
upstream.

## Visualizer

`python visualizer.py --db attempts.db --output trace-diagram.md`
renders [trace-diagram.md](../trace-diagram.md): headline numbers,
per-trace verdicts, and a Mermaid flowchart. Traces sort A-first by
trace ID, long traces collapse middle retries, and POST attempts show
method, path, bytes, and argument count only — never argument values
or bodies.

## Schema note (why db.py differs from raw v0.3)

The v0.3 `attempts` table is reused in the same `attempts.db` file —
all 11 original columns verbatim. Logging destination host,
endpoint/method, and bytes in/out (required by the sketch) has no
column to go into in v0.3, so `db.py` appends only those fields:
`dest_host`, `endpoint`, `method`, `bytes_in`, `bytes_out`, plus
`http_status` so the numeric code survives alongside the
success/failure `status`. M4 appends `outcome` and `reason` the same
way. Existing databases are migrated in place with `ALTER TABLE`
(safe for two processes opening at once). No new database, no other
schema change.

`input_tokens` is recorded only when the upstream JSON response itself
reports `usage`; `cost_dollars` stays 0.0 — never invented.
Authorization headers, API keys, and request/response bodies are
forwarded but never logged.
