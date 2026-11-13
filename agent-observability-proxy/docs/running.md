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

## CONNECT idle timeout (`--relay-timeout`)

```powershell
python proxy.py --port 8888 --relay-timeout 300   # long-idle tunnels
```

`--relay-timeout <seconds>` (float, default `30.0`) is how long a CONNECT
tunnel may stay silent — no bytes in either direction — before the proxy
closes it and logs it as a failure. Any byte resets the silence clock, so
busy tunnels are unaffected. Raise it when an upstream turn legitimately
goes quiet for longer than 30 s before answering, e.g. a long grounded
search or slow model turn that sends nothing while it works: `300` gives
such a turn five minutes of silence instead of killing it mid-turn at 30 s.
Lower it only to reap dead tunnels sooner. The default preserves the
original 30 s behaviour.

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
python -m unittest discover -s tests -v   # 60 tests
```

## Load testing

One-time setup (already done in this checkout):

```powershell
python -m venv .venv
.\.venv\Scripts\pip install locust
```

HTTP steady + burst + recovery, with verdict and exit code:

```powershell
.\.venv\Scripts\locust -f locustfile.py --headless
```

CONNECT hedge, 20 then 50 tunnels:

```powershell
python evals/connect_load.py --threads 20
python evals/connect_load.py --threads 50 --stagger-ms 1000 --hold-open 2
```

Both start their own loopback servers, use a fresh load database, and
refuse busy ports instead of sharing them. Defaults are echo 18080 and
proxy 8888 (`ECHO_PORT` / `PROXY_PORT` / `LOAD_DB` override the first;
`--proxy-port` / `--db` the second). Gaps, not built: soak or
hour-long runs, proxy restart mid-load, real agent sessions (dogfood
day, separate).
