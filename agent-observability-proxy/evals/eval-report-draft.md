# Eval report — agent-observability-proxy (draft, from existing data only)

Status: draft. No new proxy or traffic runs. Suite re-run attempted in this session (`.venv\Scripts\python.exe -m pytest tests/ -q`): 14 passed, 22 setup errors, all sandbox blocks on socket `listen` (WinError 10013) — environmental, not code failures. 36/36 not re-verifiable in this sandbox.
Numbers below are either observed in this checkout, computed from the database files in this checkout, or marked with their source (user-supplied / live-terminal).

## 1. What the proxy is

Local proxy that watches agent traffic and logs metadata only.
Source: [README.md](../README.md), [docs/architecture.md](../docs/architecture.md).

- Plain-HTTP forwarding proxy with one SQLite row per attempt (`attempts` table, see [db.py](../db.py)).
- CONNECT tunnelling (M2): raw byte relay, count bytes, never look inside. No TLS interception, no MITM. One metadata row per tunnel. Failed connect = 502 + zero-byte failure row.
- Two-agent trace (M3): Agent A calls Agent B through the proxy, B calls upstream through the proxy again, one `X-Trace-Id` across both legs. The proxy preserves a received trace ID; it does not inject one into B's downstream call.
- Allowlist + rate limit (M4): non-allowlisted destinations blocked at the proxy, never forwarded (HTTP 403, CONNECT never opened, `outcome=blocked`, `reason=not_allowlisted`). Over-limit destinations get the proxy's own 429 (`outcome=rate_limited`, `reason=rate_limited`), recovering after the window. Default 100 per 10 s per destination.
- Outcome accounting reconciles: allowed + blocked + rate_limited + other = attempts. Legacy/NULL outcomes count as `other`.
- Never logged: Authorization headers, API keys, prompt/response bodies, header values. `input_tokens` recorded only when upstream JSON reports `usage`; `cost_dollars` stays 0.0 — never invented.

Repo status (user-supplied Nov 11; git not readable and suite not re-verifiable in this sandbox): M4 + visualizer v2 + T1–T9 fixes, suite 36/36, relay-timeout fix in (commits `d68217a` and `6264618`; main HEAD is `6264618`).
Previously observed via `git log` (earlier session): HEAD `56fbcdb test: Locust HTTP + CONNECT load tests, 50/50 tunnels clean`; P1–P4 commit `e3b2b58 proxy: P1-P4 provably-equivalent refactors`. Individual T1–T9 / P1–P4 item lists: UNSOURCED in this checkout (no itemised list found).

## 2. What dogfood actually proved (routing proof)

Method: direct SQLite queries on the files in this checkout, run in this session (the `dogfood.db` block quotes the earlier `python report.py --db` output, see [report.py](../report.py); not re-run here). No new traffic.

### dogfood.db — 20 attempts, 7 allowed / 13 blocked

Observed `report.py --db dogfood.db` output in this session:

```text
allowed=7 blocked=13 rate_limited=0 other=0
attempts=20 traces=20 successes=7 success_rate=35.0% retries=0 avg_latency_seconds=28.8572 bytes_in=1813918 bytes_out=2816822 input_tokens=0 cost_dollars=0
dest_host              method  endpoint                        n   ok retry    avg_s    b_in   b_out
api.meta.ai:443        CONNECT api.meta.ai:443                20    7     0  28.8572 1813918 2816822
```

Direct SQLite grouping confirms: 7 rows `('api.meta.ai:443','CONNECT','allowed','','success')`, 13 rows `('api.meta.ai:443','CONNECT','blocked','not_allowlisted','blocked',403)`.

Proved:

- Routing enforcement works on real CONNECT traffic: non-allowlisted attempts were blocked at the proxy (403, `reason=not_allowlisted`), never forwarded.
- Allowed tunnels relayed bytes both ways and logged one metadata row each (byte counts non-zero, `bytes_in=1813918 bytes_out=2816822`).
- Outcome accounting reconciles: 7 + 13 + 0 + 0 = 20.

### dogfood-day1.db — Day 1 is 3 attempts (ids 1–3); ids 24–27 are heartbeat, excluded

Observed in this session: the file holds 7 rows with ids 1, 2, 3, 24, 25, 26, 27 — an id gap, not a contiguous run. Per user correction (Nov 11), only ids 1–3 are Day 1; ids 24–27 are post-Day-1 periodic heartbeat traffic, noted separately and excluded from Day 1. (`report.py --db dogfood-day1.db` aggregates all 7 rows, so the Day-1 and heartbeat figures below are computed with direct SQLite queries on each id set instead.)

Day 1 (ids 1–3), computed from the file in this checkout:

```text
attempts=3 successes=3 success_rate=100.0% avg_latency_seconds=23.6372 bytes_in=5180 bytes_out=38691 input_tokens=0 cost_dollars=0
```

- All 3 are `CONNECT api.meta.ai:443`, `outcome=allowed`, `status=success`.
- Times (EST): id 1 Nov 9 15:41, id 2 Nov 9 19:01, id 3 Nov 9 23:01 (file stores UTC `2026-11-09T20:41:50`, `2026-11-10T00:01:09`, `2026-11-10T04:01:10`; EST = UTC−5). User-supplied clock times match the file.
- Id 1 dominates the average (70.17 s, 3864 in / 29271 out); ids 2–3 are short (0.22 s / 0.52 s).

Heartbeat (ids 24–27), computed from the same file, excluded from Day 1:

```text
attempts=4 successes=4 avg_latency_seconds=0.2400 bytes_in=2632 bytes_out=18813 input_tokens=0 cost_dollars=0
```

- Nov 10, 03:01 / 07:01 / 11:01 / 15:01 EST (file stores UTC `08:01:10`, `12:01:11`, `16:01:11`, `20:01:11`), every 4 hours.
- 658 bytes in each; about 4710 bytes out each (4710, 4683, 4710, 4710); latency 0.18–0.30 s.
- All `CONNECT api.meta.ai:443`, `outcome=allowed`, `status=success`.

Proved (Day 1): 3/3 CONNECT tunnels to one destination succeeded end-to-end through the proxy with per-tunnel metadata rows. Nothing more.

### dogfood-day2.db — 12 attempts, 5 with status='success' (not a clean rate)

Observed in this session (direct SQLite query on the file in this checkout):

```text
12 rows, all CONNECT api.meta.ai:443, all outcome=allowed.
status=success: ids 1, 2, 5, 6, 7 (5 rows).
status=failure: ids 3, 4, 8, 9, 10, 11, 12 (7 rows).
```

- The 5 `success` rows mix control traffic with real turns (user-supplied cause split) — do not present 5/12 as a clean task success rate.
- 30 s idle kills on ids 3 and 8 (user-supplied cause; observed latencies ~30.4 s / ~30.5 s). Id 11 is a separate 138.27 s failure (1.5 MB in / 1.9 MB out), cause uncharacterised — not an idle kill. The remaining non-successes are interrupted turns (user-supplied).
- `outcome` and `status` disagree here on purpose: `allowed` is the routing decision (all 12 passed the allowlist), `status` is the turn result. Outcome accounting: 12 allowed + 0 blocked + 0 rate_limited + 0 other = 12 attempts.

### Kill-switch test — fail-closed proven two ways (Nov 10, user-supplied setup)

Setup (user-supplied; the `--relay-timeout` flag exists at [proxy.py](../proxy.py) line 519): proxy on port 8888, fresh `kill-switch-test.db`, allowlist `127.0.0.1`, `localhost`, `::1`, `api.meta.ai`, `--relay-timeout 300`.

- Prompt "say hi" with the proxy up: succeeded. Observed in this session: `kill-switch-test.db` holds exactly 2 rows, both `CONNECT api.meta.ai:443`, `outcome=allowed`, `status=success` — 100% success on the live leg.
- Proxy stopped, prompt "hello again": failed with a transport error after 4 provider attempts (user-supplied). Observed in this session: the file still holds exactly 2 rows — zero new rows while the proxy was down.

Fail-closed proven two ways: with the proxy up, traffic is logged and allowed; with the proxy down, traffic fails instead of bypassing it, and nothing is recorded as a false success.

### Load results (live-terminal-sourced, not in-repo)

- HTTP Locust: 37.1 req/s, p50 0.114 s, p95 0.762 s, 0 failures in 1427. Source: live terminal output (user-supplied Nov 11) — no run log or output file with these figures exists in the checkout (searched `locustfile.py`, `docs/`, `evals/`). Tool: [locustfile.py](../locustfile.py).
- CONNECT hedge 50/50 pass. Source: live terminal output (user-supplied Nov 11), not repo-sourced. The earlier commit subject `56fbcdb test: Locust HTTP + CONNECT load tests, 50/50 tunnels clean` (observed via `git log` in an earlier session) is a subject line only; stagger/hold-open config and per-run logs remain UNSOURCED — no run log found in checkout. Tool: [evals/connect_load.py](../evals/connect_load.py).

## 3. What dogfood did NOT prove

- Thin Day-1 signal only: single method (CONNECT), single destination (`api.meta.ai:443`), 3 attempts, zero retries, zero rate-limited rows, zero HTTP legs. The 4 heartbeat rows (ids 24–27) are periodic keepalive traffic, not task evidence. Day 2 adds 12 CONNECT attempts to the same destination (see §2) — still no `/task` → `/echo` two-agent path, no second destination, no burst/recovery exercise in dogfood data.
- No failure recovery proven by dogfood: `retries=0` everywhere observed; no 429 observed; no 502 observed in `dogfood.db`, the Day-1 rows, or the heartbeat rows. Day 2's 7 non-successes are turn-level (`status=failure`), not proxy-level rejections.
- No token/cost signal proven: `input_tokens=0 cost_dollars=0` in `dogfood.db` and the Day-1/heartbeat rows. Expected for CONNECT byte-relay (upstream never reports `usage` JSON through a tunnel), but it means cost-per-task from dogfood is a measured zero, not a priced zero — see §4.
- `trace-diagram.md` cost figures ($0.0120 total, $0.0060/success) are M1 seeded-demo output, NOT dogfood evidence, and are not used for any claim below.

## 4. Cost per successful task (only where data supports it)

Dogfood data supports exactly one cost statement:

- dogfood.db: 7 successes, `input_tokens=0`, `cost_dollars=0` → measured cost per successful task = $0.0000, with zero token usage reported.
- dogfood-day1.db: 3 successes, `input_tokens=0`, `cost_dollars=0` → measured cost per successful task = $0.0000, with zero token usage reported.

Caveat (sourced from [db.py](../db.py) lines 83–86 and [docs/architecture.md](../docs/architecture.md) lines 83–84): tokens/cost are stored only when the upstream JSON response reports `usage`. A CONNECT tunnel never yields such JSON, so $0.0000 here means "no usage signal passed through the tunnel", not "the upstream agent spent nothing". Real per-task price: UNSOURCED — no usage data in either scoped database.

## 5. Top 3 failure/waste categories from real traces

Scoped to `dogfood.db` + the Day-1 and heartbeat rows of `dogfood-day1.db`:

1. Non-allowlisted routing blocked — 13 of 20 attempts in `dogfood.db` (`outcome=blocked`, `reason=not_allowlisted`, HTTP 403, zero bytes forwarded). This is the proxy doing its job, but it is the dominant "failure" category by count and the main wasted-attempt surface: every blocked attempt is a task leg that never reached upstream.
2. Long-lived allowed tunnels with heavy bytes, no retries — 7 allowed successes averaging 28.86 s in `dogfood.db` (1.8 MB in / 2.8 MB out) and 3 averaging 23.64 s in Day 1 (5180 in / 38691 out, dominated by id 1). No failures, but the latency/byte weight is the only waste-adjacent signal in the data (held-open tunnels cost time and bytes per success).
3. No third failure mode observed — UNSOURCED / absent: `rate_limited=0`, `other=0`, `retries=0`, no malformed-header rows, no 502s in the scoped files. Any claim of a third category (e.g. retry storms, rate-limit waste, secret leaks) would be invented; the data shows none. Day 2's 7 non-successes are turn-level failures characterised in §2, not proxy waste categories, and are not ranked here.

## 6. Numbers used and their sources

| Number | Value | Source |
| --- | --- | --- |
| dogfood.db attempts/outcomes | 20 attempts; 7 allowed / 13 blocked / 0 rate_limited / 0 other | Observed `report.py --db dogfood.db` + direct SQLite GROUP BY, this session |
| dogfood.db success/latency/bytes | 7 successes (35.0%), avg 28.8572 s, in 1813918 / out 2816822, tokens 0, cost 0 | Same observed output |
| dogfood-day1.db Day 1 (ids 1–3) | 3 attempts, all allowed/CONNECT api.meta.ai:443, 3 successes (100%), avg 23.6372 s, in 5180 / out 38691, tokens 0, cost 0 | Computed from file in this checkout (ids 1–3 only); EST times user-supplied, match file UTC |
| dogfood-day1.db heartbeat (ids 24–27, excluded) | 4 attempts, all success, avg 0.2400 s, in 2632 / out 18813; Nov 10 03:01/07:01/11:01/15:01 EST, every 4 h | Computed from file in this checkout; excluded from Day 1 per user correction |
| dogfood-day2.db | 12 attempts, all allowed/CONNECT api.meta.ai:443; 5 status=success (ids 1,2,5,6,7), 7 status=failure | Grouping observed this session; cause split (control traffic, interrupted turns, 30 s idle kills on ids 3/8; id 11 a separate 138.27 s failure, cause uncharacterised) user-supplied — NOT a clean 5/12 task rate |
| Kill-switch test (Nov 10) | "say hi" via proxy: 2 rows, 100% success; proxy down "hello again": transport error after 4 provider attempts, 0 new rows | Row counts observed in kill-switch-test.db this session; setup, prompts, and attempt count user-supplied |
| Suite 36/36, T1–T9, relay-timeout fix | Claimed, not verified this session | User-supplied Nov 11 (commits d68217a, 6264618); suite attempt here blocked by sandbox socket-bind |
| P1–P4 | Commit exists; item details UNSOURCED | `git log` subject `e3b2b58`; no itemised list in checkout |
| HEAD 6264618 | User-supplied | git not readable in this sandbox |
| CONNECT hedge 50/50 pass | Live-terminal figure, not repo-sourced | User-supplied Nov 11; tool [evals/connect_load.py](../evals/connect_load.py) |
| Locust 37.1 req/s, p50 0.114 s, p95 0.762 s, 0 failures in 1427 | Live-terminal figures, not repo-sourced | User-supplied Nov 11; tool [locustfile.py](../locustfile.py) |
| Cost per dogfood success $0.0000 | Observed (tokens 0, cost 0) | dogfood.db `report.py` output + Day-1 computed figures above; semantics per [db.py](../db.py) |
| Real token/price cost | UNSOURCED | No `usage` signal in CONNECT data |

Open items: second dogfood workflow (different destination/method, HTTP legs, two-agent path); any rate-limit/retry evidence from real traffic; priced cost whenever an upstream reports usage; re-verification of suite 36/36 and scorer/trajectory runs where socket bind is allowed (attempted here; sandbox blocked `listen`).
