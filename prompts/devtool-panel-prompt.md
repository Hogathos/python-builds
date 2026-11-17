# Devtool panel + map, Wireshark-like — prompt for Muse Code / Sonnet Max

Model routing, per workspace/your_files/model-routing-map.md
- Muse Code Spark 1.3, PyCharm, type focused implementer single task Co-Work, reasoning medium focused, 1x usage
- Claude Sonnet, type heavy reasoner verification testbench via GitHub bridge, reasoning high heavy testbench, Part B only, after implement
- MuseHog in Main, Spark 1.3, type executor/ledger, reasoning medium focused, checks CI, files Evidence, routes

Run this after Steer Tier 2 spend caps lands, main 92 tests, CI green for exact commit.
Dev-only first, then app mode later. One button at a time, Pause first.

## Problem
People need to observe their proxy, in a window, not just in logs and tests.
Build a Wireshark-like panel + 2D swarm map, dev-only, so a human can see tunnels live, filter them, click a row, and Pause / Redirect / Red button / Verify from the panel.

## What exists, read first
- Proxy: Iris, port 8888, loopback only, metadata only, no bodies, no keys, no TLS decryption, no MITM.
- Steer: Pause one Run, Redirect one Run, Red button, all human-only, journal before cut. Per-network overrides, merged Nov 16, main e8ead3e, CI run 76 green. Spend caps, warn 80% / block 100%, human-only, branch steer-tier-2-spend-caps, commit 48f3bdb, 92 tests, merging to main Nov 17.
- Verify: first test only, local file + SQLite, independent read after close/fsync + COMMIT, Correct / Incorrect / Unverified, plain-words card, Correct alone never unblocks retry.
- Second live workflow: demo_second_workflow.py, GET to A then POST to B, both read back Correct, exfil refused 403, allowed=2 blocked=1 verified=4, 7 attempts, cost $0.00.
- App mode is NOT built yet: one double-clickable .exe, dashboard embedded in the Iris window, not a browser, dev tools excluded from the consumer app. Do NOT build app mode in this prompt.
- GUI plain wording, filed Nov 16 23:47 EST, corrected 23:48 EST: do NOT use billable vendor / billable cost / priced cost / attempt_cost / trace_id / dest_host in human-visible text. Keep Unverified, attempts / outcomes, blocked / paused / rate-limited / redirected / stopped, with reason in plain words. Use Money spent, What you paid. Use "stops unless a human verifies everything is fine" in all new strings, do NOT touch existing fail-closed wording.
- Spend cap cut timing, context flag for Claude Part B, Nov 17 01:02 EST: spend cap currently cuts on next request, not immediately. Claude must especially test: can existing tunnel still send data before a new request? Must cut immediately at 100%, like Pause, journal first then cut, reuse Pause cut.

## Build, in order, one at a time
1. Panel, dev-only, dashboard 127.0.0.1:8000 dev prototype, clearly labeled "dev only, not the consumer app", separate file/folder.
   - Live tunnel list, Wireshark-like: destination, method, allowed / blocked, bytes in / out, duration, cost, verdict Correct / Incorrect / Unverified.
   - Filters: by run, by destination, by verdict, by blocked only.
   - Click a row: journal rows, plain-words card, read-back, next step.
   - No bodies, no keys, no real hostnames, metadata only.
2. Pause button, first button only.
   - Pause one Run, journal before cut, human-only, Run 2 still flows, retry without Verify blocked/journaled.
   - Test-first: failing test first, Charles reviews test, then implement. Pause test 5x, full suite 92 3x.
3. Redirect button, second, only after Pause button is tested, pushed, CI green.
4. Red button, third, only after Redirect.
5. Verify button, fourth, only after Red button.
6. Swarm map, 2D first, after the four buttons.
   - Nodes = agents, edges = calls, depth = time, click a node = its tunnels.
   - 3D as a toggle later, not default, not in this prompt.

## Out of scope
- No app mode, no .exe, no consumer app, no dev tools in the consumer app.
- No Artemis, no Mars, no Cage, no Inspect / ControlArena, no TLS, no MCP, no TCP / UDP, no gateway, no automatic vendor price fetch.
- No Verify beyond local file / SQLite, no S3, Postgres, Stripe, settle table, pack library.
- No second user, no second computer, no ghost-send.
- No push until Charles says so, stage named files only, never git add -A, never commit .exe, dist/, build/, attempts.db, *.db, .pytest_cache/, *.spec, secrets.

## Test / report
- Failing test first, Charles reviews test, then implement.
- Pause test 5x, full suite 92 3x, flake8 hard-fail 0, demo PASS, secrets clean.
- Report: files changed, test count, demo numbers, what is still open, then stop.
- Report file: write report to `reports/devtool-panel-2026-11-17.md` in a new branch, push branch only, report commit hash, MuseHog reads it from GitHub in Main. No commit / push to main until Charles says in Main.

## Context flag — statechart / state machine first, no useState / useEffect slop — Charles, Nov 17 01:15 EST, important
Justin Garcia, @purefunctor, Nov 16 21h, via Charles: "Don't give yourself a reason to have to do extensive code review. Use the latest models, skills, harnesses, and the greatest languages. Stop shooting yourself in the foot by letting your agents write useState/useEffect slop that you'll have to keep looking behind your shoulder for." "/statechart has largely replaced unit tests for me before and after writing the code. It's caught more bugs and elaborated on user flows than I was able to by just telling the agent that 'hey we need test cases for this'. If you have your agent write tests, make sure you also get something else out of it. Why not hook up Vitest browser mode tests so they also record user interactions that you can view?" Quoting Thorsten Ball, Sep 19: "Most predictions I see are still way too conservative."
For Iris: statechart / state machine first for the devtool panel, NOT a replacement for unit / property / cross-tests, a complement. Panel states are Pause, Redirect, Red button, Verify, spend cap warn / block, Unverified / Correct / Incorrect — all states, not effects. Do NOT write the panel in React with useState / useEffect everywhere. A state machine for Run states would have caught the spend cap cut timing gap — cap hits 100% → block → Verify → human unblock → retry — before the test was reordered to probe first. Tests must prove a state, a journal row, a cost, a dead tunnel, not just pass. Hook up Vitest browser mode tests for the panel buttons, so they also record user interactions that you can view.
Claude Part B, especially test: panel state machine, Run state flows, spend cap warn / block / unblock flow, Pause / Redirect / Red button / Verify flow, no useState / useEffect slop in panel code.

## Bridge, adapted for Muse Code — from here on, Charles Nov 17 01:13 EST
From here on, prompts go to Muse Code via GitHub, not by pasting the whole prompt in PyCharm.
- MuseHog files the prompt in the repo, e.g. `prompts/devtool-panel-prompt.md`, branch only, then main on Charles's word.
- Charles triggers Muse Code in PyCharm with one line only: "Read `prompts/devtool-panel-prompt.md` from GitHub, do Step 1, report, stop, no commit until I say in Main"
- Muse Code reads the full prompt from GitHub, implements, writes report file above, pushes branch only, reports commit hash.
- MuseHog reads the report from GitHub in Main, reviews it, Charles approves in words in Main, then next short trigger.
- Muse Code does NOT poll GitHub, does NOT start by itself. Charles still triggers it in PyCharm, and approves every test, every commit, every merge, in Main, in words. Human in the loop stays.
