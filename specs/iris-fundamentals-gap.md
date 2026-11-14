# Iris fundamentals gap — what Iris is missing at the beginning

Date: 2026-11-14
Status: spec only, no code in this file. Build in Muse Code after the weekly reset, Nov 15, 2026, 7:00 PM EST, one prompt per task, plan gate, test-first, Spark 1.3 medium for known implement, high only for hard bug / load-bearing design.
Source: CyberHog / Charles, Nov 14, 2026, "Is there anything Iris is missing that it shouldn't be? Anything code fundamental wise at all, what companies usually go for? At least in the beginning."

## What Iris already has
- Tests: 78 green live in Lightcone, 79 in the repo after Nov 13 cleanup, CI green. Live text says "78 tests green, 60 old plus 18 new networking fundamentals" — verify current suite count before changing that line.
- README trimmed, 32 lines.
- License: AGPLv3, pushed, commit 44480f51f29e52aae4d5780e53239462f7e85a9f.
- SECURITY.md, local only, human in the loop, fail-closed, pushed commit aa76b9bb.
- Kill-switch, fail-closed proven.
- Priced cost live on dashboard: blocked and rate_limited always $0.00, nonzero recorded cost always wins, loopback $0.00, everything else unknown, never guessed.
- Dogfood Day 1 and Day 2, routing proof, 13 blocked / 7 allowed.

## Missing, in build order
1. **Verify and Steer — the core.** Watch is built. Verify is not built. Steer is not built. Control endpoint is HELD, not approved in words. Approve Steer + Verify together, then build Steer first, then Verify. Do not add a control endpoint before Charles says yes in words. Recommended model/effort: Spark 1.3, high.
2. **App mode.** One .exe, double-click, proxy + API start inside Iris, dashboard embedded in the Iris window, NOT in a browser, NOT at 127.0.0.1:8000 in a browser. Dev-only helpers (test button, diagnostics, raw logs, db path) are dev-only, never shipped in the consumer app.
3. **Real cost wiring.** Tokens x vendor price into cost_dollars. Automated pricing is decided, not built: auto-detect model/destination, auto-fetch published vendor prices into a local cached price file, update on startup/periodically, offline fallback = unknown, never guessed. No manual price tables.
4. **Second live workflow.** One other person running Iris, one other destination, Verify catching something real. Right now it is only Charles.
5. **SQLite pin.** Pin to 3.51.3 or higher, prefer 3.53.0, for the WAL-reset bug (SQLite 3.7.0-3.51.2). Current: 3.50.4, no WAL.
6. **Per-host relay timeout.** Noted, not built.
7. **Changelog and versioning.** So a user can see what changed and what version they are on. Right now it is commits, not releases.
8. **Error handling and logging for Iris itself.** If Iris fails, what does the user see, in plain words, and what does it log, hash-chained, no bodies, no keys.

## Out of scope for this gap list
No cloud, no swarm map, no compliance pack, no Manim marketing videos yet. Those are later, after the 8 above.
Manim plan lives separately: `~/workspace/goals/agent-network-observability-project/files/iris-manim-marketing-plan.md`
