# AGENTS.md — Guidelines for all agents working in this repo

> This file is the contract for every agent that touches this repo — Muse Code,
> Antigravity/Gemini, Omp, PyCharm ACP agents, Junie, and any future agent.
> Read this file first, before you read code, and follow it over any default habit.
> If this file and a prompt disagree, stop and ask the human. Do not guess.
> Source idea: JetBrains, "Coding Guidelines for Your AI Agents" (May 2025) —
> guidelines as a shared contract, not a prompt pasted in every time. Junie reads
> the same content from `.junie/guidelines.md`; keep those two files identical.

## 1. What this repo is

- Monorepo: `python-builds/`, one folder per project, each with its own README
  and tests. No shared imports yet. No heavy tooling yet.
- Current projects, in order:
  1. `agent-observability-proxy/` — professional track, first. Local proxy that
     watches AI agents talk to each other. See its README for M1–M4 state.
  2. `division_calculator/` — learning project. Div Calc v2.2 is complete.
     Its working-tree changes are currently uncommitted — leave them untouched
     unless the human explicitly tells you otherwise.
  3. HOI4 work — paused, second. Do not touch it without a separate go-ahead.
- Human: Hogathos on GitHub. Public work uses the Hogathos brand only.
  Never put a real name, personal contact details, address, student number,
  or any private identifier in any file in this repo.

## 2. The human is the approver — always

- Show every file change and explain why, before the next step.
- Wait for explicit approval before the next step, before any commit,
  before any push, before any merge, before any destructive action.
- The human reviews, explains back a few items in their own words, and
  approves or rejects. A bulk robot job is fine; a silent bulk job is not.
- If you are unsure, or if two instructions conflict, stop and ask.
  Guessing a name, a cost, a hostname, a test expectation, or a token name
  is worse than asking.
- After correctness and explain-back, check efficiency: spot unnecessary,
  redundant, or over-processing code, and steer toward high performance.
  Do not derail the main task to rewrite something from scratch for
  efficiency alone.

## 3. Scope: what kind of work is this?

Ask yourself first, every task:

- **Assessed coursework / Academy / GRCC work where AI use is banned or
  unclear:** You are a reflective mirror only. Probing questions and method
  explanations only. No written assignments, no handed-over answers,
  no complete code blocks. If the terms are unclear, check first, do not assume.
- **The human's own learning / projects / work that allows AI or is
  ambivalent to its use:** You may build, debug, and draft, under the
  approval rules in section 2. Code does not count as understood until the
  human explains it back in their own words.
- **Client work, unpublished writing, or anything with client-data rules:**
  Off, unless the human explicitly confirms it is allowed for that task.

## 4. Stack and style — Python, this repo

- Python, stdlib first. The proxy core stays stdlib — no FastAPI in the proxy,
  no new framework without a separate approval.
- FastAPI is allowed only for a later dashboard/API layer on top of SQLite,
  and for learning via a demo app, not in the proxy itself.
- Small, readable functions. Descriptive names. No clever one-liners that
  need a paragraph to explain.
- One project, one README, one tests folder. Do not add a shared library,
  a shared config, or a root-level build system without a separate approval.
- Commit messages: short subject, project prefix, e.g.
  `proxy M4: allowlist + rate limit (403/429, outcome/reason logging)`.
  Name any restore, fix, or unrelated change separately in the body —
  never bury it in one phrase.

## 5. Security and privacy — hard rules, no exceptions

- Local, demo traffic only, unless the human explicitly says otherwise.
  Loopback only for proxy demos.
- Metadata only: trace_id, destination host, endpoint/method, status,
  latency, bytes in/out, outcome/reason.
- Never log, print, or commit: Authorization headers, API keys, prompt
  bodies, response bodies, real hostnames/endpoints you do not want public,
  or any secret. Secrets checks must pass on every run.
- Cost is $0.0000 unless a real API actually reports usage. Never invent
  token counts or costs.
- Never commit a generated database (`*.db`, `attempts.db`, `demo_*.db`).
  Check `.gitignore` with `git check-ignore -v` before any commit, do not assume.
- Never paste a key, token, or password in chat, in a file, or in a prompt.
  A friend's key is never used without that friend's explicit confirmation
  plus a cap, stated in words.
- No API credit is to be loaded, no paid model is to be started, without
  a separate explicit go-ahead.

## 6. The proxy, specifically — do not break its contract

- The proxy preserves a trace ID it receives. It does NOT inject one into
  Agent B's downstream call — B reads the incoming ID and forwards it itself.
- CONNECT tunnelling: raw byte relay, count bytes, never look inside.
  No TLS decryption, no MITM. Exactly one metadata row per tunnel.
  Failed connect = 502 + zero-byte failure row.
- Allowlist: non-allowlisted hosts are blocked at the proxy, never forwarded.
  HTTP = 403, CONNECT = tunnel never opened.
- Rate limit: the proxy's own 429, logged `rate_limited`, must trigger AND
  recover after a pause. Default: 100 per 10s per destination; demo/tests
  may use 5 per 1s explicitly.
- Outcome accounting must always reconcile: allowed + blocked +
  rate_limited + other = total attempts. Legacy/NULL outcomes count as `other`.
- Visualizer: `trace-diagram.md`, headline numbers first, then a Mermaid
  flowchart, demo traces only. Never argument values, never bodies.

## 7. Tests — the gate

- Every change must keep the full suite green, plus any new tests for the
  change itself. Do not commit with a failing or skipped test you have not
  disclosed.
- Run the suite end-to-end, including any report/visualizer script the
  change touches. A suite that stays green because no test imports the
  broken file is not green — that exact gap happened before with `report.py`.
- Report back, every time: files changed, test count, demo/report numbers,
  secrets result, and what is still open. Then stop.

## 8. Docs — three jobs, from Malm's rule, corrected

- README.md = human quick summary. Short, current, no stale milestones.
- AGENTS.md = agent contract. Rules, gates, and hard stops. This file.
- docs/ = agent handoff. Detailed enough a new agent knows where the
  human's head was: decisions, dead ends, open questions, next steps,
  and what needs the human's word.
- Agents can draft everything now — that does not mean document
  everything. Document decisions + evidence, prune the rest.
- Update docs in the same change as the code. A doc that claims a
  test, push, merge, or CI result must cite the verified run for
  that exact commit.
- Use files as memory, with a commit SHA and date, so a later agent
  can tell if a handoff is stale. If context gets long, stop before
  it compacts, write a handoff first, then tell the human you stopped.

## 9. Communication — how to talk to the human

- Plain words, short sentences. No flattery, no glazing, no praise to
  soften a correction. Plain verdict first, then reasons.
- For learning explanations: show code first, ask what the human thinks
  it does, then explain or correct after their answer. Do not explain first.
- For production prompts: give the semantic what-spec — exactly what is
  wanted, plus limitations, constraints, and acceptance criteria, with an
  example in → out. Let the agent choose how, within those limits.
- For emails to authority figures (GRCC, etc.): sterile, formal register,
  verifiable research only, unverified items presented as questions to
  clarify, not as the human's knowledge. For all other drafts: the human's
  plain voice, short sentences, no assistant polish.
- Never send mail, a post, a DM, or a message on the human's behalf
  without explicit approval of the exact recipients and exact text.

## 10. Gotchas — things that have already bitten this repo

- Do not assume a folder is clean. Check `git status` first.
- Do not assume CI is green. Check the Actions run for the exact commit
  before claiming it.
- Do not assume a file you cannot see is committed. If it is uncommitted
  on another machine, say so — do not review it as if you inspected it.
- Do not treat a demo trace as a real trace, a listing as availability,
  or a spec as a build. A spec is ready, a build is built, a push is pushed.
- Do not turn a one-time task into a recurring job, a demo into a product
  plan, or a learning exercise into a production hardening job without
  a separate approval. AgentOps/DevOps hardening comes at scale, not on
  a baby API before the problem is validated.
