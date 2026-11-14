# Iris trace fields — Spark 1.3 build prompt

One prompt, one task. Copy-paste this whole prompt to Muse Code in PyCharm, Spark 1.3, Co-Work Mode ON, YOLO / Unrestricted ON.

## What

Add the trace fields Alok Pandey asked for in mitmproxy discussion #8587, Nov 13, 2026, and fix how CONNECT rows are shown, and fix allowlist friction.

This is trace + dashboard only. No control endpoint, no Steer build, no Verify build, no SDK, no MITM, no TLS termination, no bodies, no keys, no header values.

## Fields to add, per Run / row

1. bytes_tx and bytes_rx, split, not one bytes total.
   - bytes_tx = bytes sent out from the agent. High outbound to an unexpected host is an exfil signal.
   - bytes_rx = bytes received back. High inbound is usually a normal response / download.
   - Show both, in plain words, with their meaning. Example: "Sent 12,400 bytes, received 3,100 bytes."
2. close_reason / outcome, for every row.
   - Plain HTTP: status_code.
   - CONNECT / tunnel: close_reason, one of: success, client_eof, upstream_reset, blocked_allowlist, rate_limited, relay_timeout, unknown.
   - If the outcome is not known, show Unknown, never guess Success or Failed.
   - Show it in plain words. Example: "Ended because the agent closed it." / "Ended because it was blocked by the allowlist."
3. Timing: connect_ms and duration_ms.
   - connect_ms = time to connect, DNS / TLS handshake included.
   - duration_ms = total time for the Run / tunnel.
   - Show both, with meaning. Example: "Connected in 120 ms, total 42,650 ms."
4. Row kind: HTTP vs CONNECT, labeled honestly.
   - HTTP row: method, endpoint, attempt_count are per-request, show them as per-request.
   - CONNECT row: do NOT show method / endpoint / attempt_count as if they are per-request. A CONNECT row is one opaque tunnel. Show: "1 tunnel to api.meta.ai:443, 50 logical requests may be inside, total bytes X, lifetime Y seconds." Never invent a per-request count inside a tunnel.
   - If the number of logical requests inside a tunnel is not known, say Unknown, never guess.

## Allowlist friction fix

5. When a destination is blocked by the allowlist, surface the exact rejected host:port immediately, on that row, in plain words.
   - Example: "Blocked api.example.com:443 by the allowlist."
   - On that row, show what the human can do, in plain words: Allow this, Block this, add to list. No hunting in a log file.
   - Do not auto-allow. Human decides, logged, plain words.

## What NOT to do

- No control endpoint. API stays read-only GET: /health, /traces, /traces/{id}, /stats. No POST, no Pause / Redirect / Block build in this task.
- No MITM, no TLS termination, no decryption, no bodies, no keys, no header values in the log.
- No guessing. Unknown stays Unknown. A tunnel with 50 logical requests inside is shown as 1 tunnel, not 50 rows. A timeout is Unknown, not Failed, not Success.
- No B→C downstream fix in this task. That is Verify / SDK work, later. Do not try to see B→C from the proxy.
- No OS-level egress enforcement in this task. Name the limit in the code / README if relevant, do not build it here.
- No streaming timeout change in this task, except: keep relay_timeout configurable, do not hard-code a new blanket number. Timeout outcome stays Unknown.

## Acceptance criteria

- Suite stays green, all tests pass, report the count. Before this task: 60/60.
- New tests for: bytes_tx / bytes_rx split, close_reason values, connect_ms / duration_ms present, CONNECT row honesty (no per-request method / endpoint invented), allowlist rejected host:port shown on the row.
- Dashboard shows: per Run, bytes sent / received separately, outcome in plain words, timing in plain words, HTTP vs CONNECT labeled honestly.
- Live test: run the proxy, do a plain HTTP Run and a CONNECT Run, check the dashboard shows the new fields, and a blocked destination shows its exact host:port.
- DB: add fields to the trace row. If a migration is needed, do it safely, do not lose existing rows, do not log bodies / keys.
- Commit and push, stage named files only, never git add -A, never git commit -a, never commit .exe, dist/, build/, attempts.db, *.db, .pytest_cache/, *.spec, secrets. Report commit hash + push result + test results.

## Example in → out

In: a CONNECT Run to api.meta.ai:443, total 1,813,918 bytes in, 2,816,822 bytes out, 28.8 seconds, ended success.
Out, dashboard row: "Run f2784ae6 — 1 tunnel to api.meta.ai:443 — Sent 2,816,822 bytes, received 1,813,918 bytes — Connected in 120 ms, total 28,857 ms — Ended: success — Inside this tunnel: number of requests unknown, not guessed."

In: a blocked Run to example.com:443.
Out, dashboard row: "Run abc123 — Blocked example.com:443 by the allowlist — Sent 0 bytes, received 0 bytes — Ended: blocked_allowlist — [Allow this] [Block this]"

## Context

- Repo: Hogathos/python-builds, folder agent-observability-proxy/
- Source: Alok Pandey cold read, mitmproxy discussion #8587, Nov 13, 2026. Hils passed: "Zero capacity to review AI repos, sorry."
- Steer design file: ~/workspace/goals/agent-network-observability-project/files/iris-steer-design.md, section "Alok Pandey cold read — DIGESTED 2026-11-13"
- Labels: plain words, no trace_id without "Run", no stat without its meaning, no SWE baggage. GUI labels file: iris-gui-labels.md
