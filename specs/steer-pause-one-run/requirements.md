# Steer Pause one Run — requirements

Date: 2026-11-16. Status: built and tested, Charles reviews the diff in
Main before any push. Part of: Part 2 §8 approval (Steer first, then
Verify). One test only, test-first: the test failed before Pause
existed, Charles approved it, then Pause was implemented.

## What it does

A human pauses one Run by trace_id. The proxy stops forwarding traffic
for that Run only. Other Runs keep flowing. The pause is journaled
first (outcome paused, verdict Unknown, explicitly), then the Run's live
tunnel is cut. A retry without a fresh Verify is blocked and journaled.
After a fresh Verify, the retry is allowed and journaled.

## Acceptance criteria

1. A human-approved done clause exists before the Run, once per task
   type, as a named read-back. No approved done means Unverified, never
   Correct.
2. Pause cuts the tunnel for that Run only, by trace_id, not by
   destination, not globally. Other Runs keep flowing, tunnels and
   plain HTTP alike.
3. Pause outcome is Unverified, explicitly: a journal row with outcome
   paused, status unknown, timestamp, trace_id, destination, method,
   reason human pause or Steer pause. Metadata only, no bodies, no keys.
4. After Pause, Verify runs before retry. A retry without a fresh Verify
   is blocked with reason "verify required before retry". A fresh
   Verify journals "verify ok"; the retry is then allowed and journaled.
5. Full suite stays green: 80 old tests plus this 1 new test, no
   failing or skipped test undisclosed. Outcome accounting reconciles:
   allowed + blocked + rate_limited + paused + other = total attempts.

## Unknown vs Unverified mapping

The internal status enum is unchanged: success, unknown, failure, and
the refusal words blocked and rate_limited. The verdict mapping is:

- status success means Correct.
- status failure means Incorrect.
- status unknown means Unverified, explicitly. Never Correct, never
  Incorrect, never a guess.

Everywhere a human or evaluator sees it, unknown reads as Unverified:
the dashboard summary column says "unverified" and the status column
says "unverified"; the trace diagram keeps its tested words UNKNOWN and
UNKNOWN OUTCOME, which mean the same Unverified verdict; paused rows
read outcome paused with status unknown. Display text only was fixed.
No internal enum value was renamed: the old tests pin the enum and the
diagram words, so they stand.

## Non-goals

Redirect one Run. Red button all-stop. The Verify read-back engine (a
later test builds that; here Verify is the human gate before retry).
App mode. Cage. Mars. Artemis. Remote read profiles. Firewall and
sandbox enforcement. Those are later, separate tests, separate prompts.

## Decisions

- 2026-11-16, Pause is a plain method on the proxy state, NOT an HTTP
  route. Choice: human-only by construction, so proxied agent traffic
  cannot call it. Rejected: a POST control endpoint, because the API is
  GET-only by design and the control contract stays minimal. Why: the
  agent must never be able to pause itself or others.
- 2026-11-16, pause verdict is status unknown, explicitly. Choice: the
  Unknown state the dashboard already renders, never success, never
  failure. Rejected: inventing a new verdict value, because Unknown is
  the existing explicit Unverified state. Why: a pause alone verifies
  nothing.
- 2026-11-16, paused Runs persist across restart, never auto-resume.
  Choice: a paused_runs table loaded at startup. Rejected: memory-only
  paused state, because a restart would silently unpause a Run the
  human stopped. Why: fail-closed; the human resumes, never a timer.
- 2026-11-16, HTTP refusals for a paused Run answer 503 with outcome
  paused. Choice: 503, plain-words body, retry needs a fresh Verify.
  Rejected: 403 (that is the allowlist's meaning) and 429 (that is the
  rate limit's meaning). Why: a paused Run is neither blocked nor
  limited; the code must not lie about why.

## Notes

- 2026-11-16, Pause dest_host empty on CI run 67, one failing test.
  Cause: pause_run journaled dest_host from the journal row lookup, but
  open tunnels have no journal row yet, so the row came out empty and
  the test asserting the live destination failed. Fix, same as the Red
  button union rule: the live tunnel registry now carries each open
  tunnel's destination label, and pause_run takes it live first,
  journaled second, never empty for a live tunnel. Journal before cut
  still holds: state save plus journal commit first, socket close
  after. Redirect needs no fix: it journals the human-chosen target,
  never a lookup. Verified with the Pause test 5 times in a row plus
  the full suite 3 times in a row, no flakes.
- 2026-11-16, `.pytest_cache/` access-denied warnings on Windows are
  pre-existing, not from this change. The cache directory predates this
  work, is git-ignored, and Windows denies the write. The suite still
  passes 81 / 81 with the warnings present. No test result is hidden by
  them: failures still fail loudly.
- 2026-11-16, earlier "specs/ missing" flag was a wrong path. The specs
  live at the repo root (`specs/`), not inside `agent-observability-proxy/`.
  `iris-steer-design.md` and `iris-fundamentals-gap.md` are present there.
  Nothing was invented from memory; the design above follows those files
  plus `proxy.py`, `db.py`, and the existing test layout.
