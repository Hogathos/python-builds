# Steer Red button — requirements

Date: 2026-11-16. Status: built and tested, Charles reviews the diff in
Main before any push. Part of: Part 2 §8 approval (Steer first, then
Verify). One test only, test-first: the test failed before Red button
existed, Charles approved it, then Red button was implemented.

## What it does

A human stops all agent jobs at once. Every known Run gets a stop row
first (outcome stopped, verdict Unknown, explicitly), then every live
tunnel is cut. No Run keeps working, paused or flowing. After the
button, any traffic without a fresh human approval plus Verify is
refused and journaled: no fail-open to new Runs, and old Runs never
restart on their own. A fresh human approval plus an executed read-back
plus Verify lets one new Run through; old Runs stay stopped. The
journal is only added to, never deleted. Stop rows are metadata only
and always cost $0.00.

Plain words, for evaluators: Red button means stop all agent jobs
at once.

## Acceptance criteria

1. A human-approved done clause exists before the Run, once per task
   type, as a named read-back. No approved done means Unverified, never
   Correct.
2. Three Runs start on three loopback destinations; Run 3 is paused
   first, so the button must stop a paused Run too.
3. Red button journals one stop row per known Run first, then cuts all
   live tunnels. The journal grows, never shrinks. Nothing is deleted.
4. Every Run has a stop row: outcome stopped, status unknown, timestamp,
   trace_id, destination, method, reason human red button or Steer red
   button. Metadata only, no bodies, no keys.
5. A new Run without fresh human approval plus Verify is refused with
   503 and journaled with outcome stopped, reason "approval required
   after red button". Nothing reaches the new destination.
6. Old Runs stay stopped: approving an old trace fails, retrying one is
   blocked and journaled with reason "red button stopped". A fresh
   approval plus Verify lets one new Run through, journaled end to end.
7. Full suite stays green: 82 old tests plus this 1 new test, no
   failing or skipped test undisclosed. Outcome accounting reconciles:
   allowed + blocked + rate_limited + paused + redirected + stopped +
   other = total attempts.

## Unknown vs Unverified mapping

Same mapping as Pause and Redirect, unchanged: status success means
Correct, status failure means Incorrect, status unknown means
Unverified, explicitly. Everywhere a human or evaluator sees it,
unknown reads as Unverified: the dashboard summary column says
"unverified" for unknown rows and "stopped, approval needed for a new
Run" for stopped rows; the status column says "unverified"; the trace
diagram keeps its tested words UNKNOWN and UNKNOWN OUTCOME, which mean
the same Unverified verdict. Stopped rows read outcome stopped with
status unknown. No internal enum value was renamed: the old tests pin
the enum and the diagram words, so they stand.

## Non-goals

Verify engine. Cage. App mode. Second live workflow. Competitor tests.
Windows checklist. MCP 2026-07-28 retest. Local file and SQLite read
profiles beyond the one named read-back in the test. Bypass detection.
Settle table. Whole bench. Per-network overrides. Spend caps. Block.
Throttle. Auto-Steer. Quarantine. Detain a swarm. Steer a model. Those
are later, separate tests, separate prompts. Unblock after Red button
is also later: old Runs stay stopped in this build, by design.

## Decisions

- 2026-11-16, Red button is a plain method on the proxy state, NOT an
  HTTP route. Choice: human-only by construction, so proxied agent
  traffic cannot call it. Rejected: a POST control endpoint, because
  the API is GET-only by design. Why: the agent must never stop jobs
  itself or block a human stop.
- 2026-11-16, stop verdict is status unknown, explicitly. Choice: the
  Unknown state, never success, never failure. Rejected: inventing a
  new verdict value. Why: a stop alone verifies nothing.
- 2026-11-16, the stop gate sits before the allowlist check. Choice:
  while the button is on, every trace without fresh approval plus
  Verify is refused uniformly. Rejected: checking the allowlist first,
  because a stopped Run must not get different answers by destination.
  Why: stop means stop, for everything.
- 2026-11-16, old Runs can never be approved. Choice: approval refuses
  any trace with journal rows, and only a trace with no rows at all can
  be approved. Rejected: approving by recency or by human override,
  because that would restart a stopped Run on a technicality. Why: old
  Runs stay stopped, only genuinely new Runs return.
- 2026-11-16, stopped state persists across restart, never auto-lifts.
  Choice: a red_button_state table loaded at startup, same shape as the
  pause and redirect tables. Rejected: memory-only flag, because a
  restart would silently lift the stop. Why: fail-closed; the human
  stopped everything, only a later build unblocks.
- 2026-11-16, the journal is append-only under Red button. Choice: stop
  rows are added per known Run; nothing is deleted, attempts.db stays.
  Rejected: clearing rows or the database on stop. Why: the stop must
  leave proof, and deleting evidence would destroy the audit trail.

## What is still open

Red button unblock (human-only lift) is the next decision, not this
build. Then Verify engine. Everything in Non-goals above.
