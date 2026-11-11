# Agent Observability Proxy

Local proxy that watches agent traffic and logs what happened, metadata only.

- Traces requests across agent legs with one `X-Trace-Id`.
- Blocks non-allowlisted destinations (403, never forwarded).
- Rate-limits hot destinations (429, recovers after the window).

**Never logs request/response bodies, API keys, or header values.** No TLS interception, no MITM.

Status: M4 + visualizer v2 + T1–T9 fixes. Suite 36/36.

## Quick start

```powershell
python server.py --port 18080        # terminal 1: local test server
python proxy.py --port 8888          # terminal 2: proxy on 127.0.0.1:8888
python client.py                     # terminal 3: demo traffic via proxy
python report.py --db attempts.db    # headline metrics
```

## Tests

```powershell
python -m unittest discover -s tests -v   # 35 tests
```

## Docs

- [Architecture](docs/architecture.md): M1–M4, trace propagation, schema.
- [Running the demos](docs/running.md): two-agent, M4, visualizer commands.
- [Trace diagram](trace-diagram.md): latest demo output (headline + Mermaid).
