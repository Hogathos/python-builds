# Steer Redirect one Run — requirements

Date: 2026-11-16. Status: built and tested, Charles reviews the diff in
Main before any push. Part of: Part 2 §8 approval (Steer first, then
Verify). One test only, test-first: the test failed before Redirect
existed, Charles approved it, then Redirect was implemented.

## What it does

A human moves one Run to a new allowlisted loopback destination, by
trace_id. The proxy stops sending that Run to the old destination and
sends it to the new one instead. Other Runs keep their routes. The
redirect is journaled first (outcome redirected, verdict Unknown,
explicitly), then the Run's live tunnel is cut and later traffic for
that trace_id goes to the new destination. A redirect to a
non-allowlisted destination is refused and journaled, and the Run stays
exactly where it was. A retry on the new destination without a fresh
Verify is blocked and journaled. After a fresh Verify, the retry is
allowed and journaled.

## Acceptance criteria

1. A human-approved done clause exists before the Run, once per task
   type, as a named read-back. No approved done means Unverified, never
   Correct.
2. Redirect moves that Run only, by trace_id, from A to C, both
   loopback. Run 2 still flows to B, unchanged, with no redirect row.
3. Redirect outcome is Unverified, explicitly: a journal row with
   outcome redirected, status unknown, timestamp, trace_id, new
   destination, method, reason human redirect or Steer redirect.
   Metadata only, no bodies, no keys.
4. A redirect to a non-allowlisted destination is refused with outcome
   blocked, reason "redirect refused: not allowlisted". The Run stays
   on its current destination. Nothing fails open.
5. After Redirect, Verify runs before retry on the new destination. A
   retry without a fresh Verify is blocked with reason "verify required
   before retry". A fresh Verify journals "verify ok"; the retry is
   then allowed and journaled.
6. Full suite stays green: 81 old tests plus this 1 new test, no
   failing or skipped test undisclosed. Outcome accounting reconciles:
   allowed + blocked + rate_limited + paused + redirected + other =
   total attempts.

## Unknown vs Unverified mapping

Same mapping as Pause, unchanged: status success means Correct, status
failure means Incorrect, status unknown means Unverified, explicitly.
Everywhere a human or evaluator sees it, unknown reads as Unverified:
the dashboard summary column says "unverified" for unknown rows and
"redirected, retry needs a fresh Verify" for redirected rows; the
status column says "unverified"; the trace diagram keeps its tested
words UNKNOWN and UNKNOWN OUTCOME, which mean the same Unverified
verdict. Redirected rows read outcome redirected with status unknown.
No internal enum value was renamed: the old tests pin the enum and the
diagram words, so they stand.

## Non-goals

Red button all-stop. The Verify read-back engine (a later test builds
that; here Verify is the human gate before retry). App mode. Cage.
Mars. Artemis. Remote read profiles. Firewall and sandbox enforcement.
Bypass detection. Settle table. Local file and SQLite read profiles
beyond the one named read-back in the test. Windows checklist. MCP
2026-07-28 retest. Second live workflow. Competitor tests. Whole bench.
Those are later, separate tests, separate prompts.

## Decisions

- 2026-11-16, Redirect is a plain method on the proxy state, NOT an
  HTTP route. Choice: human-only by construction, so proxied agent
  traffic cannot call it. Rejected: a POST control endpoint, because
  the API is GET-only by design. Why: the agent must never be able to
  redirect itself or others.
- 2026-11-16, redirect verdict is status unknown, explicitly. Choice:
  the Unknown state, never success, never failure. Rejected: inventing
  a new verdict value. Why: a redirect alone verifies nothing.
- 2026-11-16, refused redirect leaves the Run where it was. Choice: the
  mapping is only replaced after the allowlist check passes, and the
  refusal is journaled as blocked. Rejected: falling back to the old
  destination or failing open to the refused one. Why: the refused
  destination was never approved, and silently moving the Run back
  would undo human work.
- 2026-11-16, redirect mapping persists across restart, never silently
  undone. Choice: a redirected_runs table loaded at startup, same shape
  as paused_runs. Rejected: memory-only mapping, because a restart
  would silently send the Run back to the old destination. Why:
  fail-closed; the human chose the destination.
- 2026-11-16, the redirect stays in force after Verify. Choice: the
  mapping persists and the Verify stamp stays with it, so later retries
  on the new destination keep working until the next redirect. A pause
  is forgotten on resume; a redirect is a standing route. Rejected:
  clearing the route on resume, because that would send the Run back
  without a human word. Why: resume means continue where the human put
  it.

## What is still open

Red button. Verify engine. Everything in Non-goals above.
