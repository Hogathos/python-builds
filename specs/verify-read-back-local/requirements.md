# Verify read-back, local file + SQLite — requirements

Date: 2026-11-16. Status: built and tested, Charles reviews the diff in
Main before any push. Part of: Part 2 §8 approval (Steer + Verify
approved together, Steer built first, Verify now). One test only,
test-first: the test failed before Verify existed, Charles approved it,
then Verify read-back was implemented. Local file + SQLite only.

## What it does

A human-approved done clause exists once per task type. The agent acts.
Verify reads the effect back independently, after close/fsync and
COMMIT, and says Correct, Incorrect, or Unverified. The call row is
journaled before anything is read. The verdict row follows. An
Incorrect verdict stops the Run. Verdict and retry permission stay
separate: only a fresh Verify through the gate allows a retry. No
scores, no LLM-as-judge, no percentages, no "probably correct".

Plain words, for evaluators: Verify means check what the agent said it
did, against what actually happened, by reading it back, and say
Correct, Incorrect, or Unverified.

## Acceptance criteria

1. A human-approved done clause exists before the Run, once per task
   type, as a named read-back. No approved done means Unverified, never
   Correct.
2. Verify reads back by independent read, after settle, after
   close/fsync and COMMIT: local file text compare, local SQLite SELECT
   in a fresh transaction. Not from the agent's claim, log, score, or
   model.
3. Read matches claim, every part checked against the real effect, all
   passed: verdict Correct, journaled, with a plain-words card (claim,
   what was read, from where, as of when, verdict Correct, one-line
   why, next step).
4. Read contradicts claim, miss in a fresh transaction, row or file
   does not exist: verdict Incorrect, the Run is stopped, journaled,
   with a plain-words card.
5. Read cannot be done: no approved done, no read profile, remote with
   no local proof. Verdict Unverified, journaled, with a plain-words
   card. The evaluator is notified through the card and the dashboard,
   which both read Unverified explicitly.
6. Journal before call: the call row carries the idempotency key and
   sorts before the verdict row. Verdict and Retry-allowed are separate:
   a Correct verdict alone never allows a retry; without a fresh Verify
   the retry is blocked and journaled.
7. Retry after a fresh Verify, with the human-approved done clause, is
   allowed and journaled. The old Run stays stopped or paused until
   Verify. Nothing restarts on its own.
8. Full suite stays green: 83 old tests plus this 1 new test, no
   failing or skipped test undisclosed. Outcome accounting reconciles:
   allowed + blocked + rate_limited + paused + redirected + stopped +
   verified + other = total attempts.

## Unknown vs Unverified mapping

Same mapping as Pause, Redirect, and Red button, unchanged: status
success means Correct, status failure means Incorrect, status unknown
means Unverified, explicitly. Verify verdict rows use the status enum
as the verdict directly: Correct journals status success, Incorrect
journals status failure, Unverified journals status unknown. Everywhere
a human or evaluator sees it, unknown reads as Unverified: the
dashboard summary column says "unverified" for unknown rows and
"verified Correct", "verified Incorrect", or "unverified" for verified
rows; the status column says "unverified"; the trace diagram keeps its
tested words UNKNOWN and UNKNOWN OUTCOME, which mean the same
Unverified verdict. No internal enum value was renamed: the old tests
pin the enum and the diagram words, so they stand.

## Read profiles (v1: local only)

- Local file: read the bytes on disk after the writer closed and
  synced. Text compare against the claim. Missing file contradicts the
  claim. Unreadable file is Unverified, not a contradiction.
- Local SQLite: open a new connection on the same host, SELECT in a
  fresh transaction, after the writer committed. Compare rows as lists.
  Missing row contradicts the claim. Missing database file contradicts
  the claim. A failed query is Unverified, not a contradiction:
  addressing and credential errors are excluded, never Incorrect.
- Remote, default Do Not: a remote claim with no local proof is
  Unverified, even with an approved done clause. Remote effects stay
  Unverified unless something local proves them. V1 has public read
  plus human confirm only. An opt-in read-only credential, in the OS
  store, used only by an explicit Check, never logged, is later work,
  not v1.

## Settle

Local strong reads settle at once: the test writes, syncs, commits,
then Verify reads. No sleep is needed and none is taken. Settle times
for other destinations belong to the settle table, which is later work,
not this test. A read attempted before settle would be Unverified, not
a verdict against the agent.

## Non-goals

All other read profiles: S3, Postgres primary, Stripe direct GET,
GitHub, Slack, Gmail, Notion, public web. Settle table. Pack library.
Collections. Cage. App mode. Second live workflow. Competitor tests.
Windows checklist. MCP 2026-07-28 retest. Bypass detection. Whole
bench. Per-network overrides. Spend caps. Block. Throttle. Auto-Steer.
Quarantine. Detain a swarm. Steer a model. Those are later, one read
profile at a time, separate tests, separate prompts. The two
semantic-correctness reports live in Main workspace files, not in the
repo, and were not copied in: nothing was invented from them.

## Decisions

- 2026-11-16, Verify is a plain method on the proxy state, NOT an HTTP
  route. Choice: human-only by construction, same as Pause, Redirect,
  and Red button. Rejected: a POST control or verify endpoint, because
  the API is GET-only by design. Why: the agent must never verify
  itself.
- 2026-11-16, verdict rows reuse the status enum as the verdict.
  Choice: Correct is status success, Incorrect is status failure,
  Unverified is status unknown. Rejected: a separate verdict column,
  because the mapping doc already defines exactly this meaning and the
  old tests pin the enum. Why: one truth, shown everywhere the same way.
- 2026-11-16, Incorrect stops the Run through the existing Pause.
  Choice: reuse pause_run with reason Steer pause, so the stopped Run
  gets the whole Pause machinery (cut tunnel, 503, Verify before
  retry). Rejected: a separate stop path for Verify, because two stop
  paths would drift apart. Why: one stop, one gate, one story.
- 2026-11-16, verify verdicts are a new outcome, verified, in counts,
  stats, report, demo, and dashboard, at $0.00. Choice: verified rows
  reconcile like every other outcome. Rejected: leaving them in other,
  because other means legacy or unknown shape, and verify rows are
  first-class. Why: the accounting must add up with no hidden rows.
- 2026-11-16, file and database misses are Incorrect, query failures
  are Unverified. Choice: a miss contradicts the claim; a failure to
  read contradicts nothing. Rejected: treating all misses as
  Unverified, because an agent that claims a row it never wrote must be
  stopped, not shrugged at. Why: contradiction stops, inability to read
  asks a human.
- 2026-11-16, the Verify engine never stamps retry permission. Choice:
  only the Verify gate (verify_run) allows a retry. Rejected: letting
  a Correct verdict unblock retries by itself, because the verdict is
  about the past and the gate is about the next action. Why: verdict
  and permission stay separate by design.

## What is still open

The next read profile, one at a time. Then the Verify engine beyond
single reads. Then Red button unblock. Everything in Non-goals above.
