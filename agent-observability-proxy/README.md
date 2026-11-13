# Agent Observability Proxy

Local proxy that watches agent traffic and logs what happened, metadata only.

- Traces requests across agent legs with one `X-Trace-Id`.
- Blocks non-allowlisted destinations (403, never forwarded).
- Rate-limits hot destinations (429, recovers after the window).

**Never logs request/response bodies, API keys, or header values.** No TLS interception, no MITM.

Status: M4 + visualizer v2 + T1–T9 fixes. Suite 60/60.

## Quick start

```powershell
python server.py --port 18080        # terminal 1: local test server
python proxy.py --port 8888          # terminal 2: proxy on 127.0.0.1:8888
python client.py                     # terminal 3: demo traffic via proxy
python report.py --db attempts.db    # headline metrics
```

## Tests

```powershell
python -m unittest discover -s tests -v   # 60 tests
```

## Docs

- [Architecture](docs/architecture.md): M1–M4, trace propagation, schema.
- [Running the demos](docs/running.md): two-agent, M4, visualizer commands.
- [Trace diagram](trace-diagram.md): latest demo output (headline + Mermaid).

## Handoff

How to run it:

```powershell
python proxy.py --port 8888 --db attempts.db --allowlist 127.0.0.1,localhost,::1 --rate-limit 100 --rate-window 10 --relay-timeout 30
```

Defaults: port 8888, db attempts.db, allowlist `127.0.0.1,localhost,::1`, rate limit 100 per 10 s, relay timeout 30.0 s (see `proxy.py` argument defaults). Point a tool at it with `HTTP_PROXY=http://127.0.0.1:8888`.

How to read a trace: `python report.py --db attempts.db` (see `report.py`): one SQLite row per attempt, metadata only — trace_id, destination, method, status, latency, bytes in/out, outcome, attempt number. Never prompts, bodies, keys, or Authorization headers.

What it can't see: TLS is opaque — a CONNECT tunnel logs destination / timing / size only, no decrypted payload, no per-request detail inside a tunnel. No priced cost — tokens 0, cost $0.0000 measured, no usage signal through a tunnel.

Evidence: suite 60/60; Locust 37.1 req/s with 0 failures in 1427; dogfood Day 1 3/3; Day 2 12 attempts / 5 success; kill-switch passed fail-closed; eval report + golden dataset v2 in `evals`, commits 7e39e2c and e4fca47.
