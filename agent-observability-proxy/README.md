# Agent Observability Proxy

Local proxy in the middle of agent traffic, so the log is real traffic.
Built milestone by milestone from the 2026-11-01 proxy sketch.

## Status: M3 (awaiting approval before M4)

M1 is a plain-HTTP forwarding proxy to a local test server with
metadata-only SQLite logging. M2 adds CONNECT tunnelling: the proxy
accepts `CONNECT host:port`, opens a raw TCP tunnel, and relays bytes
both ways so HTTPS traffic can pass through. The tunnel is never
decrypted (no TLS interception, no MITM), and only metadata is logged
per tunnel: destination host:port, method CONNECT, success/failure,
latency, bytes in/out, and the trace ID (carried on the CONNECT
request, or generated and returned in the `X-Trace-Id` response
header). Payload content, headers, and keys are never logged.
M3 adds the two-agent trace demo: Agent A calls Agent B through the
proxy, and Agent B calls the upstream test server through the proxy
again, with one `X-Trace-Id` carried across both legs. If A sends no
trace ID, the proxy generates one on the first leg, returns it, and
that same ID is forwarded to B and carried on B's downstream call.
Every attempt from both legs is logged under that one trace_id, with
dest_host / endpoint distinguishing the A leg (Agent B's /task) from
the B leg (upstream /echo). Run it with `python demo_two_agents.py`
or the tests in `tests/test_trace_propagation.py`; Agent B standalone
is `python agent_b.py --port 18081`. No allowlist / rate limit /
block test (M4) yet.

## Schema note (why db.py differs from raw v0.3)

The v0.3 `attempts` table is reused in the same `attempts.db` file —
all 11 original columns verbatim. Logging destination host,
endpoint/method, and bytes in/out (required by the sketch) has no
column to go into in v0.3, so `db.py` appends only those fields:
`dest_host`, `endpoint`, `method`, `bytes_in`, `bytes_out`, plus
`http_status` so the numeric code survives alongside the
success/failure `status`. Existing v0.3 databases are migrated in
place with `ALTER TABLE`. No new database, no other schema change.

`input_tokens` is recorded only when the upstream JSON response itself
reports `usage`; `cost_dollars` stays 0.0 — never invented.
Authorization headers, API keys, and request/response bodies are
forwarded but never logged.

## Run M1

```powershell
python server.py --port 18080        # terminal 1: local test server
python proxy.py --port 8888          # terminal 2: proxy on 127.0.0.1:8888
python client.py                     # terminal 3: demo traffic via proxy
python report.py --db attempts.db    # GROUP BY headline metrics
```

Or point any tool at it: `HTTP_PROXY=http://127.0.0.1:8888`.

Trace ID: an incoming `X-Trace-Id` is forwarded unchanged; otherwise
the proxy generates one, adds it upstream, and returns it in the
`X-Trace-Id` response header. Repeats of the same trace + endpoint +
method inside 10 s are logged as attempt 2, 3, ... with
`retry_reason='retry'`.

## Tests

```powershell
python -m unittest discover -s tests -v
```
