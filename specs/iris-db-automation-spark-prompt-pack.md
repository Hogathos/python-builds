# Iris DB automation — Spark prompt pack

Model/effort every time: Muse Spark 1.3, medium for plan / implement, low for review unless load-bearing then high.
Run after weekly reset Nov 15, 7:00 PM. Weekly was 7% left Nov 13 23:58. Do NOT run tonight.
One prompt per task. No drip-feed. Co-Work safeguards stay: stage named files only, never git add -A, never git commit -a, never commit .exe, dist/, build/, attempts.db, *.db, .pytest_cache/, *.spec, secrets. Report commit hash + push result + test results. Verbose comments kept.

## Prompt 1 — Plan gate, no code yet
Plan only, do not write code yet. Read specs/db-automation/requirements.md and iris-db-research-adas-report-2026-11-13.md (§1-§5).
Give: files to create / change, order, risks, out of scope, test list.
Charles approves the plan, then Prompt 2 implements it.

## Prompt 2 — Implement, test first
Implement the approved plan. Write the failing test first, show it, Charles reviews the test, then implement.
Build a script that fetches pinned sources only, parses exact matches only, drafts entries with source + date + version per entry to a draft file for human review. It does NOT add entries to the live DB on its own.
Rules: no guessed entries, no lookalikes, no MITM sources, no auto-import, no live DNS/API at runtime, no auto-update from untrusted sources, offline fallback local copy only.
Do NOT wire DBs into Steer / Control. Do NOT codify §5 unresolved items. Do NOT change proxy / api / db / visualizer / division_calculator.
Commit per step, named files only, report hash + push + test count.

## Prompt 3 — Review, named risks
Review this diff for these specific risks only: invented entries, wrong source/date, unpinned versions, auto-add to live DB, MITM sources, score-as-verdict, live DNS/API lookup, auto-update from untrusted sources.
List each finding as a separate candidate, do not apply fixes automatically. Charles accepts / rejects / rewrites item by item.
