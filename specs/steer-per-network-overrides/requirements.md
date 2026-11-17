# Steer per-network override — requirements

Date: 2026-11-16. Status: built and tested in worktree steer-tier-2-1,
Charles reviews the diff in Main before any commit. Part of: Steer
Tier 2, per-network overrides first, spend caps later, one at a time.

## What it does

A human sets an override for one network (one destination, host plus
port), separate from other networks. The pause action is built: live
tunnels on that network are cut, later traffic for it is refused with
503, other networks keep flowing. The override is journaled first,
then enforced. Retries need a fresh Verify, through the existing gate.

## Acceptance criteria

1. A human-approved done clause exists before the Run, once per task
   type, as a named read-back. No approved done means Unverified, never
   Correct.
2. Override keys on the full destination, host plus port, never host
   alone. A rule for 127.0.0.1:9001 never touches 127.0.0.1:9002.
3. Journal before the override takes effect: pause rows commit first,
   then live tunnels are cut. No live socket for the network remains.
4. A non-allowlisted name is refused AND journaled: outcome blocked,
   reason "non-allowlisted override name", dest = the name as given.
5. New tunnels to the overridden network are refused with 503.
6. A retry on the overridden network without a fresh Verify is blocked
   and journaled. A Correct verdict alone never unblocks a retry; only
   verify_run stamps permission. The allowed-after-verify case is a
   later test, named here, not tested here.
7. Pause rows carry the live destination, never ''. The tunnel registry
   is written before the CONNECT 200 is answered; pause reads live
   first, journaled second.
8. Every pause row and every blocked row costs $0.00. Accounting
   reconciles with the existing outcomes; no new outcome was added.

## Unknown vs Unverified mapping

Same mapping as Pause, Redirect, Red button, and Verify, unchanged:
status success means Correct, status failure means Incorrect, status
unknown means Unverified, explicitly. Override pause rows read outcome
paused with status unknown. The dashboard already renders unknown as
unverified. No internal enum value was renamed.

## Non-goals

Allow, block, and redirect actions are named in the method contract for
later tests, not pinned here. Spend caps (warn 80%, block 100%). Tier 3
and above. Cross-tests with Pause, Redirect, Red button, Verify (Part B
Claude). Per-network overrides beyond pause. Red button unblock.
Anything in the Tier 2 prompt's out-of-scope list.

## Decisions

- 2026-11-16, override reuses the Pause machinery, not a new gate.
  Choice: paused traces, 503 refusals under outcome paused, existing
  Verify-before-retry. Rejected: a parallel override state machine,
  because two gates would drift apart. Why: one pause, one gate.
- 2026-11-16, rules persist across restart. Choice: an override_rules
  table loaded at startup, same shape as every other Steer table.
  Rejected: memory-only rules, because a restart would silently lift
  the override. Why: fail-closed.
- 2026-11-16, a non-allowlisted name is refused AND journaled under no
  trace. Choice: the refusal names a destination, not a Run, so it
  journals outside any trace. Rejected: journaling it under an
  unrelated Run's trace, which would lie about who did what. Why: the
  journal must name the thing it acted on.
- 2026-11-16, register-before-200 for every tunnel. Choice: the live
  tunnel registry is written before the 200 answer, so no Steer action
  can land in the gap. Rejected: leaving the race, because Pause
  already proved it journals '' and cuts nothing. Why: journal first
  means the registry first.
- 2026-11-16, the Gap 13 red-button fix rides in this branch. Choice:
  stop rows take live destinations first, journaled second, same union
  rule as Pause fix 54498fc. Rejected: leaving live-only traces with
  empty stop rows. Why: a stopped Run with no destination is not proof.

## Test correction, disclosed

- The non-allowlisted refusal first journaled under an empty trace,
  and the test searched all rows for it. Per Charles: the refusal gets
  its own override-attempt trace_id (`override::<name>`), exactly one
  row, no Run invented. Test pins that trace_id, dest, and outcome
  directly. Stated here for approval.

## What is still open

Allowed-after-verify_run test. Cross-tests (Part B). Spend caps next,
only after this is approved. Red button unblock. Everything in Non-goals.
