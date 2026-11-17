# Steer spend caps — requirements

Date: 2026-11-16. Status: built and tested in worktree
steer-tier-2-spend-caps, Charles reviews the diff in Main before any
commit. Part of: Steer Tier 2, second half, after per-network
overrides. One test, test-first, then implemented only after approval.

## What it does

A human sets a spend cap in dollars for one network. The cap is
journaled first, then enforced. At 80% of recorded spend the proxy
journals a warn row and lets the run continue. At 100% it journals a
block row, cuts live tunnels, refuses new ones with 503, and the retry
stays blocked until a fresh Verify. A human unblock after Verify lets
the run retry and journals the lift. Unverified costs never count
toward a cap and are never guessed.

## Acceptance criteria

1. A human-approved done clause exists before the Run, once per task
   type, as a named read-back. No approved done means Unverified, never
   Correct.
2. set_cap journals first (reason "cap set $X.XX"), no agent-callable
   route, cap keyed host + port, persisted, positive dollars only.
3. At 80%: one warn row (outcome warned, carrying what was spent),
   run continues, next call flows.
4. At 100%: block row (outcome blocked, $0.00), live tunnels cut, new
   tunnels refused 503, retry blocked and journaled.
5. A Correct verdict alone never unblocks a retry; only verify_run
   stamps permission. Human-only unblock after Verify; retry allowed,
   unblock journaled.
6. Cost rules: listed outcomes always $0.00, nonzero recorded cost
   wins, loopback $0.00, Unverified never counted, never guessed.
7. Caps are per network. A cap on A never touches B.
8. Fresh proxy, fresh temp DB per test, no attempts.db in the repo.
9. Full suite reconciles: allowed + blocked + rate_limited + paused +
   redirected + stopped + verified + warned + other = total attempts.

## Unknown vs Unverified mapping

Same mapping as everything before, unchanged: status unknown means
Unverified, explicitly. Warned rows read outcome warned with status
unknown. The dashboard says "warned, money spent at 80% of cap" and
"unverified" for unknown rows. No internal enum value was renamed: the
old tests pin the enum, so they stand.

## Human wording, filed

New human-visible strings use plain words only: no billable vendor, no
priced cost, no attempt_cost, no trace_id, no dest_host. Verdicts and
outcomes read paused, blocked, unverified, warned, with the reason in
plain words. New strings say "money spent" where money is shown, and
stops say the run "stops unless a human verifies everything is fine".
Existing fail-closed wording elsewhere was left untouched.

## Non-goals

Spending the cap (no real billing anywhere; recorded provider costs
only). Automatic vendor price fetch. Tier 3 and up. Cross-tests (Part B
Claude). Anything in the Tier 2 prompt's out-of-scope list.

## Decisions

- 2026-11-16, enforcement happens on the request path. Choice: each
  new tunnel/request re-totals recorded spend and warns or blocks
  there. Rejected: background watcher, because a watcher races the
  traffic it judges. Why: the gate sees the same destination the
  request is about to use.
- 2026-11-16, warn rows carry the cumulative total. Choice: the warn
  row's cost is what was spent, not $0.00. Rejected: a $0.00 warn row,
  because then the warning would not say what triggered it. Why: a
  warning that hides the number is not a warning.
- 2026-11-16, the cap itself is journaled as a plain row (outcome
  empty, reason "cap set $X.XX"). Choice: audit the human action like
  any other control. Rejected: silent in-memory caps, because an
  auditor must see who set what. Why: every control journals first.
- 2026-11-16, unblock forgets the rule and unpauses the cap's traces.
  Choice: lift means the human takes responsibility and the run
  resumes. Rejected: keeping the rule while unpausing, because the
  next request would instantly re-block and the unblock would be a lie.
  Why: unblock means unblocked, said out loud in the journal.
- 2026-11-16, the test probes before asserting the cut. Choice: the
  gate lives on the request path, so the probe that trips the block
  comes first and the dead-tunnel assert follows the cut it caused.
  Rejected: asserting the cut before any new request, because nothing
  runs the gate until a request arrives. Why: test what the design
  does, not what it cannot do.

## What is still open

Spend caps on real provider costs (needs the price feed that is not
built). Per-destination settle for cost rows. Red button unblock.
Cross-tests (Part B). Tier 3 and up.
