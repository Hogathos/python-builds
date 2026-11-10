# Running the demos

All commands run from this folder. Traffic is local and demo-only.

## M1: proxy in the middle

```powershell
python server.py --port 18080        # terminal 1: local test server
python proxy.py --port 8888          # terminal 2: proxy on 127.0.0.1:8888
python client.py                     # terminal 3: demo traffic via proxy
python report.py --db attempts.db    # GROUP BY headline metrics
```

Or point any tool at it: `HTTP_PROXY=http://127.0.0.1:8888`.

## M3: two-agent trace

```powershell
python demo_two_agents.py            # A -> proxy -> B -> proxy -> upstream
python agent_b.py --port 18081       # Agent B standalone
```

Covered by `tests/test_trace_propagation.py`.

## M4: allowlist + rate limit

```powershell
python demo_m4.py                    # allowlist, 403, 429 burst, recovery
```

## Visualizer

```powershell
python visualizer.py --db attempts.db --output trace-diagram.md --seed-demo
```

## Tests

```powershell
python -m unittest discover -s tests -v   # 35 tests
```
