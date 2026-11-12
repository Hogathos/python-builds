# Second dogfood plan (weeks 9–16 after funding)

Status: plan only. No workflow run, no code change, no dates set.

## Goal

A second real workflow through the proxy, different from Day 1 / Day 2, to get
rate-limit / retry evidence and priced cost — which the first run could not
produce (Day 1–2 were CONNECT-only to one destination; retries 0; no 429;
tokens 0, cost $0.0000 measured).

## Workflow

- Different destination / method from `api.meta.ai:443` CONNECT-only.
  Exact destination: TBD.
- Include HTTP legs (not tunnels only).
- Include a two-agent `/task` → `/echo` path, so M3 is exercised with real
  traffic, not just the lab 2-row trace.
- Run cadence and volume: TBD.

## Capture per day, from SQLite only

- Attempts, traces, successes, retries.
- Retry waste: tokens / cost per successful task, not per call.
- p50 / p95 latency.
- Blocked hosts (403).
- Rate-limited bursts (429).
- Whether any block was a false positive.
- Failure categories from real traces (top 3).

## Deliverables

- A short eval report in the repo.
- Golden dataset v3 from real traces (never silently edit v1 or v2).
- Visualizer update, only if the new traces justify it.

## Success bar

An evaluator who has never seen the repo can read the report, reproduce the
numbers, and point to one real failure the proxy caught or one real waste
number it cut. If it finds nothing, say that too.

## TBD (not yet decided — do not treat as planned)

- Destination(s), method mix, run cadence, volume.
- Rate-limit settings for the run (demo values vs proxy defaults).
- Which upstream reports usage (needed for priced cost).
- Start date, per-day schedule, report due date.
