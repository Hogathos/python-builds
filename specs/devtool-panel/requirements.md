# Devtool panel + Pause button — requirements

Date: 2026-11-17. Status: built and tested, Charles reviews the diff
in Main before any commit. Part of: devtool panel prompt, Step 1 and
Pause button first, one button at a time.

## What it does

A dev-only dashboard on loopback that shows what Iris sees, live:
runs with destination, method, outcome in plain words, bytes, seconds,
money spent, verdict. Filters by run, destination, verdict, blocked
only. Clicking a run opens its journal rows, the plain-words card,
and the next step. One Pause button per flowing run. The button calls
devpanel.pause_run, a plain human-only function in the same local
process. The main API stays GET-only: no control route was added there.

## Acceptance criteria

1. Panel listens on loopback only, says "dev only, not the consumer
   app" on the page, lives in its own devpanel folder.
2. Pause button pauses exactly the clicked Run, cuts its live tunnel,
   refuses new tunnels with 503, leaves other Runs flowing.
3. Pause journal row: outcome paused, status unknown, Unverified
   explicitly. A Correct verdict alone never unblocks a retry; only
   verify_run stamps permission.
4. No bodies, no keys, no real hostnames. Plain words only.
5. Full suite stays green: 92 old tests plus this 1 new test.

## Unknown vs Unverified mapping

Same mapping as everything before, unchanged: a run with no read back
is Unverified, explicitly. The panel shows Correct, Incorrect, or
Unverified per run, and "unverified" for rows nothing checked yet.

## Human wording, filed

Same rules as the main dashboard: no billable vendor, no priced cost,
no attempt_cost, no trace_id, no dest_host, no hyphenated jargon in
human-visible text. Runs read "Run XXXXXXXX". Money reads "Money
spent" and "What you paid". Stopping reads "stops unless a human
verifies everything is fine". Existing fail-closed wording untouched.

## Non-goals

Redirect, Red button, Verify buttons (later steps, one at a time).
App mode, consumer app, .exe. 3D swarm map (2D later, toggle after).
Vitest browser tests for panel clicks (Part B Claude).

## Decisions

- 2026-11-17, the button calls a plain function, not a route on the
  main API. Choice: devpanel.pause_run in-process, one dev-only POST
  in the dev-only app that does nothing but call it. Rejected: a
  control endpoint on the main API, because agents can reach the API
  and must never reach a control. Why: the function is human-only by
  location; the API stays a read-only witness.
- 2026-11-17, run states come from a small machine, not row flags.
  Choice: states.py folds each journal into one state and one verdict,
  and the button reads only the state. Rejected: per-row ifs in the
  template, because scattered conditions drift from the rules they
  show. Why: states first, effects follow.
- 2026-11-17, server-rendered HTML, no frontend framework. Choice:
  forms and links, zero JavaScript. Rejected: any component framework,
  because a dev tool needs no client state at all. Why: nothing to
  hydrate means nothing to go stale.

## What is still open

Redirect, Verify buttons. Swarm map 2D. Vitest browser tests. App mode.
