# Iris competitor verification report

**Verdict, plain:** none of the four products I could run meets the Iris 7-part criteria. The fifth, Omnitrace, could not be tested. The honest claim stays **"none found in ~20 candidates"**, never "no tool exists".

- **Status:** RUN, NOT PUSHED. Verification only. No Iris code touched, no tests run on Iris, no Lightcone edits, no paid signup, no API key, no real credential, no real destination.
- **Date:** 2026-11-16 (session date). The sandbox clock ran 2026-11-16T17:54Z to 2026-11-17T04:20Z because the sandbox paused between steps. Candidates 1 and 2 ran about 22:50Z to 22:58Z, tau2-bench about 04:16Z to 04:20Z.
- **Runner:** Claude in a claude.ai chat sandbox. Linux x86_64, Python 3.12.3, Node v22.23.4. No Docker, firejail, bwrap or nsjail. Network limited to package registries and GitHub.
- **Input:** `iris-competitor-verification-prompt.md` (filed 2026-11-16) and the run instructions in chat.
- **Metadata only:** excerpts show tool names, flags, status codes, counts, key names, and the first characters of hashes. No argument values, no result bodies, no keys or tokens, no real hostnames.

## Scoreboard

| # | Candidate | Verdict on the Part 2 claim | Version / commit | Iris 7-part criteria met |
|---|---|---|---|---|
| 1 | SafeNode | **CONFIRMED**: spawn, replace, deny-before-forward as gateway mechanics. Its hosted policy engine: **COULD-NOT-VERIFY** (needs an API key) | `3497b6d`, 2026-10-18; npm 0.1.2 | 0 of 7 |
| 2 | MCPKernel | **CONFIRMED**: `:8000/mcp` is an MCP endpoint and policy-checks calls before forwarding | PyPI 0.3.0, uploaded 2026-05-25 | 0 of 7 |
| 3 | mcp-airlock | **CONFIRMED**: lease check over stdio, in code and live. Two corrections: it is a tool server, not a gateway; leases are self-issued | `30fa2cf`, 2026-04-03; 0.1.0 | 0 of 7 |
| 4 | Omnitrace | **COULD-NOT-VERIFY**: hosted Databricks SaaS, no self-serve free tier, no live test possible. Docs-only read done 2026-11-17 (section 4a) | none (hosted) | none shown live |
| 5 | tau2-bench | **CONFIRMED** (skeptic finding): state read yes, three-valued verdict no, production gateway no | `c06b07d`, 2026-11-10; 2.0.0 | 0 of 7 |

## What matters most

1. **A landed effect reported as an error, with no Unknown.** SafeNode (S7) and MCPKernel (B) returned an error for a write that had landed. MCPKernel did the same unprompted (A1) for every call to an upstream whose tools declare an output schema. None marked it Unknown, none read anything back. This is the Iris "timeout after a commit = unknown, verify before retry" case, seen live.
2. **No committed journal before egress, anywhere.** SafeNode writes a local decision line before forwarding, but best-effort: an unwritable log did not stop forwarding, bypassed calls write nothing, and the line records intent, not outcome. MCPKernel and mcp-airlock write after the call. tau2-bench keeps the trajectory in memory and saves finished simulations only.
3. **MCPKernel's taint-label policy rules cannot gate the call that carries the taint.** The policy hook (priority 1000) runs before the taint hook (900), so the label does not exist yet when the rule is evaluated. A `sandbox` action blocks the call and never sandboxes it. Denied calls leave no audit row.
4. **SafeNode evaluates every `tools/call` in a hosted API.** Argument keys and scrubbed values leave the machine in the default mode. There is no local policy evaluation. The README's "raise mode crashes the gateway" is contradicted live.
5. **tau2-bench confirms the skeptic's reading and adds three details.** A task with no evaluation criteria scores 1.0. A run that ended early scores 0.0 even when the correct effect had landed. The evaluator can raise instead of returning a score.

## How to read the verdicts

- **Verdict on the claim:** CONFIRMED / CONTRADICTED / COULD-NOT-VERIFY / UNTESTED-PAID, about what the Part 2 report said.
- **7-part matrix cells** use the same four words about the sentence "this product does criterion N as Iris defines it". CONTRADICTED means tested and it does not. The nearest behavior seen is listed under the matrix so nothing is lost.
- **UNTESTED-PAID was not used.** No paid gate was reached. Omnitrace is COULD-NOT-VERIFY for an access and identification reason, explained in its section.

## Method and fixtures (mine, throwaway, outside the Iris repo)

- **Local upstream MCP server** with five tools: `ping`, `read_note`, `write_note`, `delete_note`, and `write_then_die`, which commits a file write and then kills its own process before replying. It logs metadata only (event, tool name, time, and how many lines or rows a product's log held when the call arrived).
- **Scripted MCP client** reading a Claude Desktop style config (`mcpServers.<name>.command/args/env`). Claude Desktop is not available in the sandbox, so this is a stand-in. For SafeNode and mcp-airlock the config contains only the product's entry, as the READMEs describe.
- **Independent read-back in my tests** means I listed the scratch directory myself after each scenario. No product did it for me.
- **All data is synthetic.** Placeholder values were used wherever a product demanded a key or secret. None is a credential.
- **Fixture scripts live only in the sandbox** and reset between tasks. I can export them on request.

## 7-part matrix

Each cell is the verdict on "this product does criterion N as Iris defines it".

| # | Criterion | SafeNode | MCPKernel | mcp-airlock | Omnitrace | tau2-bench |
|---|---|---|---|---|---|---|
| 1 | Claim intake | CONTRADICTED | CONTRADICTED | CONTRADICTED | COULD-NOT-VERIFY | CONTRADICTED |
| 2 | Per-Run human-approved "done" clauses | CONTRADICTED | CONTRADICTED | CONTRADICTED | COULD-NOT-VERIFY | CONTRADICTED (a) |
| 3 | Hold on mutating calls with no definition | CONTRADICTED (b) | CONTRADICTED (c) | CONTRADICTED (d) | COULD-NOT-VERIFY | CONTRADICTED (e) |
| 4 | Settle-time-aware independent read-back | CONTRADICTED | CONTRADICTED | CONTRADICTED | COULD-NOT-VERIFY | CONTRADICTED (f) |
| 5 | Three-valued Correct / Incorrect / Unverified, no scores | CONTRADICTED | CONTRADICTED | CONTRADICTED | COULD-NOT-VERIFY | CONTRADICTED (g) |
| 6 | Committed journal before egress | CONTRADICTED (h) | CONTRADICTED (i) | CONTRADICTED (j) | COULD-NOT-VERIFY | CONTRADICTED (k) |
| 7 | Stop the Run only on Incorrect | CONTRADICTED | CONTRADICTED | CONTRADICTED | COULD-NOT-VERIFY | CONTRADICTED |

Nearest behavior seen:

- **(a)** tau2: success criteria (golden actions, environment assertions) are authored per task before the run. Closest thing to "done clauses" in the set. They are benchmark ground truth, not approved by a human per Run.
- **(b)** SafeNode: a `review` decision holds a call ("Held for human review"). It comes from the hosted policy, not from a missing definition. The gateway does not tell mutating from read-only tools. With the evaluator unreachable, the default fail-closed mode blocks everything.
- **(c)** MCPKernel: `default_action: deny` blocks tools no rule mentions (live). There is no hold or approve state. A `sandbox` action blocks.
- **(d)** mcp-airlock: `require_capability` denies a guarded tool call that carries no lease (live). It is a deny, not a hold, and the caller can mint the lease itself.
- **(e)** tau2: no hold. A task with no criteria returns 1.0 (E7).
- **(f)** tau2: an independent state read exists (replay of the log into a fresh environment, then a DB hash compare, live). It reads a simulated DB, not a real destination, and has no settle delay.
- **(g)** tau2: each component is 1.0 or 0.0, an early-ended run is 0.0, and the evaluator can raise. No Unknown.
- **(h)** SafeNode: the only pre-forward write seen in the set, and still best-effort (see section 1).
- **(i)** MCPKernel: the audit row is committed per call, but after the upstream call, and blocked calls get no row.
- **(j)** mcp-airlock: hash-chained and tamper-evident, but the allowed-path event is written after the tool ran.
- **(k)** tau2: no per-call persistence. Finished simulations are checkpointed.

---

## 1. SafeNode

**Verdict: CONFIRMED** on "gateway spawns upstreams, replaces client entries, denies before forward". **COULD-NOT-VERIFY** on its hosted policy engine (needs an API key; none used).

| Field | Value |
|---|---|
| Repo | `github.com/sp3ak/safenode-mcp-gateway`, TypeScript, 13 commits |
| Commit tested | `3497b6da06a1baf3edd6d1a5713b2c7c58a568ea`, 2026-10-18T16:17:22+07:00 ("README: copy SKILL.md, not a folder") |
| Published build | npm `safenode-mcp-gateway` 0.1.2, gitHead `8a740375b8a81fbb56cf5344d65f83dd99947cc9`. `git diff --stat` of `src/` and `package.json` from that gitHead to the tested commit is empty, so I tested the code `npx` runs. Later commits are Docker demo, registry metadata, SKILL.md |
| Runtime | Node v22.23.4; MCP SDK 1.30.0 (gateway side), Python MCP SDK 1.30.0 (my client); negotiated protocol 2025-11-25 |
| Date checked | 2026-11-16 (sandbox clock about 22:50Z) |

### Code read (src/*.ts, README)

- **Spawn exists.** `gateway.ts` starts each configured downstream server through the SDK's stdio client transport and merges their tool lists. It is not echo-only.
- **Glama's "echo-only" explained.** The repo ships a Docker demo config that proxies `examples/echo-server.mjs`, added for registry health checks. Introspecting that image shows one tool, `echo`. Reproduced live (S0).
- **Order inside `callTool`:** evaluate, then write the local decision line, then forward. `bypass: true` tools return before the log write.
- **Evaluation is remote.** Every `tools/call` is POSTed to a hosted evaluation API (default base URL in `src/config.ts`, overridable by `baseUrl` or `SAFENODE_BASE_URL`) with a bearer key. No key means a config error at start. There is no local policy engine.
- **Decisions:** `allow`, `warn`, `review`, `deny`. The evaluator result type also carries risk and impact score fields (code only, the hosted response was never seen).
- **Fail modes** per config or per tool: `fail_closed` (default), `fail_open`, `raise`.
- **Decision log** is `appendFileSync` of one JSON line, no fsync, failure swallowed ("best-effort"). The `forwarded` flag is computed from the decision before the forward happens.
- **grep** for verify, read-back, postcondition, outcome, settle, journal, fsync in `src/`: nothing relevant (the hits are the TypeScript `unknown` type).

### Commands run

```
git clone https://github.com/sp3ak/safenode-mcp-gateway sn ; git log -1
npm ci --ignore-scripts ; npx tsc ; node dist/index.js --version   # 0.1.2
npm test                                                           # SafeNode's own suite: 74 passed, 5 files
# client config = Claude Desktop shape, ONE entry:
#   {"mcpServers":{"safenode":{"command":"node","args":[".../dist/index.js","--config",".../gw.json"],"env":{"SAFENODE_API_KEY":"<placeholder>"}}}}
# gw.json "servers" holds my local upstream (the entry that was replaced)
python fixtures/drive.py client-sN.json safenode steps-sN.json stderr.log      # scenarios S0..S7
node dist/index.js --config gw-s2.json --dry-run                               # envelope shape
npm view safenode-mcp-gateway version gitHead ; git diff --stat <gitHead> HEAD -- src package.json
```

### Scenarios and log excerpts (metadata only)

**S0, repo demo config (bundled echo server), evaluator pointed at a closed local port**
```
tools/list  -> ["echo"]
tools/call echo -> isError=true  head="Blocked by policy."  (fail_closed, evaluator unreachable)
stderr: connected to "demo" (1 tools) / "echo" BLOCKED by the fail_closed policy, without evaluation.
```

**S1, my upstream, evaluator unreachable; `ping` = fail_open, `read_note` = bypass, rest fail_closed**
```
tools/list -> [delete_note, ping, read_note, write_note, write_then_die]   (upstream was spawned by the gateway: upstream log shows ev=spawn)
write_note  -> isError=true  "Blocked by policy."        upstream saw: nothing
delete_note -> isError=true  "Blocked by policy."        upstream saw: nothing
ping        -> isError=false (forwarded, unevaluated)    upstream saw: call, decision-log lines on disk at receipt = 3
read_note   -> isError=false (bypass by config)          upstream saw: call, decision-log lines on disk at receipt = 3  (no new line: bypass writes none)
decision log: 1 write_note deny degraded=true forwarded=false | 2 delete_note deny degraded=true forwarded=false | 3 ping allow degraded=true forwarded=true
my read-back of the scratch dir: 0 files (the blocked write did not land)
```

**S2, local STUB evaluator at 127.0.0.1 (my decisions, not SafeNode's): write_note=allow, ping=warn, read_note=review, delete_note=deny. Default payload mode.**
```
order per call: stub receives eval request -> gateway writes decision line -> (only allow/warn) upstream receives call
write_note  allow  forwarded   upstream saw call, decision-log lines on disk at receipt = 1
ping        warn   forwarded   upstream saw call, lines = 2; client text carries a "[SafeNode warning]" prefix
read_note   review NOT forwarded  client: isError=true "Held for human review."; upstream saw nothing
delete_note deny   NOT forwarded  client: isError=true "Blocked by policy.";     upstream saw nothing
my read-back: the file from the allowed write exists, so the denied delete did not run.
what the gateway sent to the stub: envelope keys [action_type, context, payload]; payload keys [name, text] (scrubbed string values);
  context keys include tool_name, server_name, session_id, payload mode, redaction counts; Authorization scheme "Bearer" (value not logged); UA safenode-mcp-gateway/0.1.2
```

**S3, stub says allow, but the local decision-log path is a directory (unwritable)**
```
stderr: one warning that the log could not be written, then "continuing without local logging"
write_note x2 -> both FORWARDED, both executed (upstream saw 2 calls; my read-back shows both files)
the log path stayed an empty directory.   => the local journal is not a gate on egress.
```

**S4, `failMode: raise`, evaluator unreachable**
```
write_note -> protocol error from the gateway ("fetch failed")      upstream saw nothing
ping       -> same protocol error from the SAME live process        => the gateway did NOT crash. README says raise "crashes the gateway": CONTRADICTED live (v0.1.2).
```

**S7, crash after commit: stub says allow; `write_then_die` writes the file then kills the upstream before replying**
```
write_then_die -> client isError=true, text starts: server "iris-test-upstream" failed to run "write_then_die" (MCP error -32000)
my read-back: the file EXISTS (the effect landed)
decision log: write_then_die allow forwarded=true   (intent flag; no outcome, no Unknown, no read-back)
next call ping (upstream now dead): decision log says forwarded=true again; client gets the warning prefix plus the same failure text
```

**S5, `--dry-run` (what would leave the machine)**
```
payloadMode=redacted      -> payload keys [note, path], string values scrubbed, redaction counts {email:1}
payloadMode=metadata_only -> payload values replaced by sha256 hashes, redaction counts kept
```

### Pass / fail

- **Candidate pass criterion** ("spawn + deny-before-forward demonstrated with log"): **PASS**. Spawn shown from a client config that contains only the gateway entry. Deny-before-forward shown by the upstream log (no receipt for denied calls) and by my read-back. Caveat: the deny decisions came from fail-closed on an unreachable evaluator and from my stub, not from SafeNode's engine.
- **Iris 7-part:** 0 of 7. Nothing takes a claim, nothing holds a Run to approved done-clauses, no read-back, no three-valued verdict, no committed journal, no Run to stop.

### What remains unresolved

- Real policy decisions, real response shape (the score fields), latency, quotas: the hosted API needs a key. The README says the free tier needs no card. Signup was not done under the no-keys rule.
- The `review` approval flow (dashboard) cannot be exercised without the hosted service.
- Windows behavior (cmd shims, PID handling) untested. Claude Desktop itself not used.

---

## 2. MCPKernel

**Verdict: CONFIRMED.** `localhost:8000/mcp` answers as an MCP proxy endpoint and policy-checks calls before forwarding.

| Field | Value |
|---|---|
| Package | PyPI `mcpkernel` 0.3.0, uploaded 2026-05-25 (latest on PyPI at run time). Requires Python >=3.12 and `mcp` >=1.23,<2; resolved `mcp` 1.30.0 |
| Date checked | 2026-11-16 (sandbox clock about 22:54Z to 22:58Z) |
| Hooks (from `/status`) | policy 1000, taint 900, context 850, dee 800, sandbox 750, audit 100, observability 50 |

### Code read

- `_run_security_pipeline`: pre-execution hooks, then upstream call, then post-execution hooks, then the log phase. If a pre-execution hook aborts, it returns early, so post and log phases never run for blocked calls.
- Policy engine is local and deterministic: YAML rules with `tool_patterns`, `argument_patterns`, `taint_labels`, actions `allow | deny | audit | sandbox | warn`; most restrictive match wins; no match falls to `default_action` (config default `deny`).
- Audit logger: SQLite table `audit_log`, hash-chained, one commit per entry, arguments stored as key names only.
- The MCP-SDK-facing `_call_tool` returns only a list of text content, never `isError` and never structured content.

### Commands run

```
uv venv mk-venv ; uv pip install mcpkernel            # 0.3.0
mcpkernel serve --host 127.0.0.1 --port 8000          # exactly as filed, no config, empty cwd
curl -D - http://localhost:8000/mcp ; curl http://localhost:8000/mcp/ ; curl /health /status /tools
mcpkernel serve --host 127.0.0.1 --port 8000 --config mk.yaml   # with stdio upstream (my fixture) + policy file
python fixtures/drive_http.py http://localhost:8000/mcp/ steps.json   # MCP Streamable HTTP client
curl -X POST http://127.0.0.1:8000/mcp/legacy -d '<JSON-RPC tools/call>'
sqlite3 (read-only) audit.db                          # my read of the audit rows
```

### Excerpts (metadata only)

**As-shipped start (no config).**
```
log: mcpkernel proxy started, mode=standalone, upstream_count=0; warning: no valid policy paths to watch
creates dee_store/traces.db and dee_store/audit.db in the cwd
GET /mcp   -> 307 Temporary Redirect to /mcp/ (content-length 0, vary: Origin, server: uvicorn)
GET /mcp/  -> 400, JSON-RPC error -32600 "Bad Request: Missing session ID"; response carries an mcp-session-id header
GET /health -> 200 {status: healthy, service: mcpkernel, version: 0.3.0, mode: standalone}
GET /tools  -> {"tools": []}
```

**Startup bug, v0.3.0.** Putting `policy.policy_paths` in the YAML config crashes startup: `AttributeError: 'str' object has no attribute 'exists'`. The loader assigns YAML values without converting paths. Workaround used: the environment variable `MCPKERNEL_POLICY__POLICY_PATHS`.

**With config + stdio upstream.** `initialize` OK (server name `mcpkernel`, protocol 2025-11-25, session id issued). `tools/list` passes the five upstream tools through.

**A1, upstream tools typed (they declare an output schema), 7 calls.**
```
every call -> isError=true, 79 chars, identical hash: "Output validation error: outputSchema defined but no structured output returned"
the 4 policy-allowed calls DID execute upstream (upstream log; my read-back shows the files) and the 3 blocked calls did not.
=> the client sees the same error for a landed write and for a blocked call, and cannot tell them apart.
```

**A2, upstream tools without an output schema (removes that confound). Policy: read_note allow; ping action=sandbox; write_note allow; delete_note deny; write_note with taint_labels [pii] deny; unlisted tools fall to default deny.**
```
 1 read_note                 allow   forwarded
 2 write_note (clean)        allow   forwarded, file landed
 3 delete_note               deny    NOT forwarded; client isError=false, text starts "[BLOCKED] Policy denied: [MK-DENY-DELETE] ..."
 4 write_note, args contain an email-shaped string, rule "deny if taint pii"
                             ALLOWED, FORWARDED, file landed. Policy matched 1 rule (the allow). Taint was detected after the policy ran; the audit row records labels [pii].
 5 read_note of a note whose content is email-shaped
                             returned unmodified, isError=false. Taint detected post-execution, labels [pii] in the audit row. Not blocked.
 6 ping, rule action=sandbox NOT forwarded, NOT sandboxed: "[BLOCKED] Policy denied: [MK-SANDBOX-PING] ..."
 7 write_then_die (unlisted) NOT forwarded: default deny
legacy POST /mcp/legacy: delete_note -> HTTP 403, JSON-RPC error -32003; read_note -> HTTP 200, isError=false
audit DB: 5 rows for 10 calls. Rows exist only for forwarded calls; the 4 blocked calls produced no row.
  row fields: tool, action allow, outcome success, taint_labels, arguments_keys (keys only), agent anonymous
journal order: audit rows committed when the upstream received call 1..5 = 0, 1, 2, 3, 4 (the current call's row did not exist yet)
```

**B, argument-regex control rule + crash after commit.**
```
write_note with an email-shaped text arg, rule argument_patterns {text: "@example\.com"} -> deny, NOT forwarded. Pre-call policy on argument values works via regex, not via taint labels.
write_then_die (allowed) -> upstream committed the file then died. Client: text "Upstream server error", isError=false. My read-back: file EXISTS.
audit row for it: outcome=error (not unknown). Next read_note -> "Upstream server error" again, outcome=error.
```

### Pass / fail

- **Candidate pass criterion** ("`localhost:8000/mcp` responds as an MCP proxy endpoint and policy-checks a call; fail if the port does not exist, or only post-execution taint with no pre-call policy"): **PASS**. The port is a flag (config default is 8080). `/mcp` redirects to `/mcp/`, which is session-based Streamable HTTP. Pre-call policy shown by deny, default-deny and argument-regex cases with no upstream receipt. Part 2's "post-execution taint" is also CONFIRMED, for results.
- **Iris 7-part:** 0 of 7. Nearest: default-deny and a pre-call policy gate; a SQLite audit commit per call, but after egress.

### What remains unresolved

- Sandbox backends (Docker, Firecracker, WASM): no Docker here, never exercised. With a `sandbox` rule the call is blocked, so the sandbox hook did not run.
- Sigstore signing (set off), OAuth audience binding, auth modes, rate limits, `--transport stdio`, DEE replay and drift, eBPF, trust and behavior scoring modules (present in the package, not run).
- The output-schema failure is specific to SDK 1.30.0 plus typed upstream tools. I did not test other SDK versions.
- Windows untested.

---

## 3. mcp-airlock

**Verdict: CONFIRMED** that a capability-lease check runs over stdio, in code and live. **Two corrections to the Part 2 framing:** it is a self-contained tool server, not a gateway in front of other MCP servers; and the caller mints its own lease.

| Field | Value |
|---|---|
| Repo | `github.com/lara-muhanna/mcp-airlock`, 3 commits, no tags |
| Commit tested | `30fa2cfd9c53d80f6f03048f6d88c2bf4054e7ab`, 2026-04-03T23:15:16-05:00 |
| Version | 0.1.0, standard library only, no dependencies |
| Protocol | hard-coded `protocolVersion` "2025-03-26" in its own JSON-RPC loop (no SDK, no negotiation) |
| Date checked | 2026-11-16 (sandbox clock between about 22:58Z and 04:16Z) |

### Files the Part 2 run never fetched, read in full

- `docs/CLIENT_SETUP.md`, `examples/client-configs/claude_desktop.mcp.json`, `examples/client-configs/cursor.mcp.json`. Both client configs launch `python -m mcp_airlock --config <path> serve` as a stdio server. The setup doc lists six expected tools and a `demo` smoke test.
- `grep -i lease` hits: README, `docs/SANDBOXING_AGENTIC_APIS.md`, and the `airlock_issue_capability` tool description in `server.py`. `capabilit` appears across `server.py`, `cli.py`, `policy.py`, `capability.py`.
- **Not a proxy:** `git grep -i -E 'subprocess|popen|stdio_client|upstream|forward|reverse.?proxy|spawn' -- mcp_airlock` returned exit 1, no matches. Its tools are built in: `http_get_json`, `weather_hourly`, and four `airlock_*` tools.

### Code read

- A lease is an HS256-signed token with claims `capability_id, session_id, subject, tools, nbf, exp, intent_hash, constraints`.
- Every guarded `tools/call` must carry two extra arguments, `_capability` (the token) and `_context` (session, subject, intent). The caller supplies both, including the intent text.
- The policy denies with codes such as `capability_required`, `intent_mismatch`, `session_mismatch`, `tool_not_in_capability_scope`, `invalid_capability`. A regex prompt-injection check produces a numeric risk score per call.
- Logging: denied calls are logged before returning. Allowed calls are logged after `tool.call()` ran. The ledger append is a plain file append, no fsync.
- `http_get_json` accepts HTTPS only and refuses loopback and private addresses.

### Commands run

```
git clone https://github.com/lara-muhanna/mcp-airlock air ; git log -1
uv venv air-venv ; uv pip install -e .                 # 0.1.0, no dependencies
python -m mcp_airlock --config examples/airlock.config.json demo     # the documented smoke test
python -m mcp_airlock --config airlock.config.json verify-log
python fixtures/drive_airlock.py                       # stdio client -> unmodified server, observer wrapper (see Deviations)
python fixtures/airlock_schema_probe.py                # advertised schema + a schema-conformant call
```

### Excerpts (metadata only)

**Documented smoke test (`demo`, repo example config).**
```
handshake OK, 6 tools, lease issued
"normal request" did not complete: name resolution failed (sandbox has no public DNS), so the allowed path ended at the network
attack simulation (intent change, risk, domain) BLOCKED
audit log integrity VALID ; usage stats: 2 calls, 0 allowed, 1 denied ; exposure score 57.25 "medium"  (a numeric score)
```

**Live stdio run, my config (guarded tools require a lease; allowed domain list = localhost only).**
```
initialize -> server mcp-airlock 0.1.0, protocol 2025-03-26
tools/list -> [airlock_audit_tail, airlock_exposure_report, airlock_issue_capability, airlock_usage_stats, http_get_json, weather_hourly]
T1 http_get_json, no lease                  -> isError=true  violations [capability_required]
T2 airlock_issue_capability (a plain tool call, no approval step) -> lease issued; claim keys [capability_id, constraints, exp, intent_hash, nbf, session_id, subject, tools]; token not printed
T3 valid lease + matching _context + allowed domain -> policy ALLOWED, tool EXECUTED, then the tool's own guard refused: "Blocked non-public target IP" (event tool_failed)
T4 same lease, intent changed               -> intent_mismatch
T5 same lease, other session                -> session_mismatch
T6 lease scoped to weather_hourly, call http_get_json -> tool_not_in_capability_scope
T7 tampered signature                       -> invalid_capability, "Invalid capability signature."
T8 30 s lease, waited 36 s                  -> invalid_capability, "Capability expired."
T9 lease for tools ["*"], asked 99999 s     -> issued, no approval; granted 1800 s (the configured max)
```

**Ledger (11 events, in write order).** `tool_denied` (capability_required), `capability_issued`, `tool_failed`, `tool_denied` (intent), `tool_denied` (session), `capability_issued`, `tool_denied` (scope), `tool_denied` (signature), `capability_issued`, `capability_issued`, `tool_denied` (expired). `verify-log`: "OK: provenance log chain is valid."

**Journal order, observed.** An observer on name resolution inside the tool's execution (server code unmodified) saw **2 ledger lines on disk** when the allowed call started executing. That call's own event (`tool_failed`) is line 3, written after.

**Advertised schema vs what the lease needs.**
```
http_get_json inputSchema: properties [query, url], required [url], additionalProperties=false; description does not mention leases
a call that follows the advertised schema exactly (no _capability, no _context) -> isError=true, [capability_required]
```
So in a standard client (the Claude Desktop config in the setup doc), every call to a guarded tool is denied unless the model emits undeclared `_capability` and `_context` fields, which the schema forbids.

### Pass / fail

- **Candidate pass criterion** ("capability-lease check demonstrated in code and in a live run; fail if no lease code found"): **PASS**.
- **Iris 7-part:** 0 of 7. The lease is self-issued by the caller, so it is not a human-approved done-clause. `intent` is self-attested. There is no read-back and no verdict. Tamper-evident hash chain, but after execution.

### What remains unresolved

- The success path against a real public HTTPS destination: the sandbox has no public DNS and the tool refuses loopback, so the `tool_allowed` event with its output hash was never seen live. `weather_hourly` was not called.
- Cursor client not used. Windows untested (the Claude Desktop sample uses a Windows-style path).

---

## 4. Omnitrace

**Verdict: COULD-NOT-VERIFY.** Nothing was installed or run. This is not UNTESTED-PAID: no paid gate was reached.

**Why I stopped, in order:**

1. **No target.** The filed prompt carries the homepage quote ("Read-back proof") and no URL or package name. The Part 2 source list was not an input to this run, and web research was off limits.
2. **The name collides.** What the registries return under "omnitrace" is not the candidate:

   | Where | What it is | Check I ran | Result |
   |---|---|---|---|
   | npm `omnitrace` 1.1.1 | "Open-source, privacy-first AI log debugger" (repo `adityv/omnitrace`) | tarball downloaded with `npm pack --ignore-scripts`, grepped | 0 hits for REGRESSED, read-back, unverified. 3 hits for "settle": a boolean variable in `src/demo.js` |
   | PyPI `omnitrace` 0.1.1 | "multimodal attribution for generative models" | wheel downloaded without installing, grepped | 0 hits |
   | GitHub repo-name search | 68 repos; top results are a profiler (ROCm/omnitrace) and unrelated tools | metadata only | none described as agent read-back verification |

3. **Egress is allowlist-only** (package registries and GitHub). A non-allowlisted host returned no response (http 000), so a SaaS signup or API would be blocked.
4. **Signup needs an identity.** Creating an account means an email address under your name or an invented one. Not done under the no-credentials rule.

**To run test 4 next time, I need either:** the exact product URL or package name from the Part 2 source list plus its domain allowed in the sandbox network settings, or a run from a networked machine.

**Test plan ready for that run (free tier only):**

1. Local file write by an agent action; record whether the product re-reads the target after the action.
2. Alter or delete the file after the write; record the verdict and whether it says REGRESSED, Incorrect, Unknown or nothing.
3. Make the read fail (permission denied, missing path); record Unknown handling versus pass versus fail.
4. Record the destination list, the settle delay and whether it is configurable, and the clause model (who writes the clause, when, human-approved or not).
5. Record whether the verdict set is Correct / Incorrect / Unverified or binary, and whether any score appears.

**Remains unresolved:** everything. Omnitrace is the only Track B candidate that claimed YES-READ for production use, so it is the open uncertainty under the "none found in ~20" claim.


### 4a. Omnitrace follow-up, 2026-11-17: docs-only read, hard stop at the free-route gate

**Verdict: COULD-NOT-VERIFY** (not UNTESTED-PAID). Product identified with the URL from your setup brief. Pages read: homepage, pricing, docs, architecture, agents (`/product`), autonomous-remediation solution page, and the June 2026 blog post, all at `www.omnitrace.io`. `app.omnitrace.io` (login) was not opened. No account, no signup, no Databricks connection, no credentials, nothing run.

**What it is, from its own pages:** a hosted SaaS for Databricks (FinOps and Reliability agents, "Atlas Playbook" and worker agents, MCP-orchestrated write tools, Jira approval flow). No installable package, repo or MCP server is offered. Destinations: Databricks live now; Amazon EMR "coming next"; Snowflake and Starburst on the roadmap.

**Gate that stopped the live test:**
1. **No self-serve free tier.** Pricing has Pilot ("Free during proof", design partner, requested through Contact sales), Team (usage-based, "Talk to us") and Enterprise (custom). The pilot starts with "read-only Databricks discovery" against real Databricks usage.
2. Every path in (pilot, pricing, sales contact) needs an email identity and a real Databricks footprint. I did not do that without your word.
3. Whether Databricks Free Edition could feed it is not established. Nothing on the pages says it can; the pages describe system tables, billing usage and workspace APIs, and I did not check what Free Edition exposes.

**Claims as written (source pages, exact wording kept short), not live-confirmed:**
- Read-back, homepage and `/product`: "Two-tier verification reads back the post-action state. If the change didn't stick, the agent flags REGRESSED and notifies your team." Homepage: "checks the target state after every action and keeps verification evidence with the finding and action record."
- Blog (June 2026): "A Databricks API acknowledgement is not proof." Examples: after setting a warehouse auto-stop value it reads the warehouse configuration; after terminating a cluster it confirms the cluster state; for table maintenance it "should compare the next telemetry window with the expected outcome". That last case is a later comparison, not an immediate read, so "after every action" is looser than the homepage line.
- Capability list on the homepage: "Scheduled polling, targeted read-back checks, and outcome evidence." Apply-to-verify target "3-5 min" (the homepage card says 5 min). No settle delay is documented as a setting.
- Clause model: autonomy modes per strategy (manual, approval required, auto low-risk) with dollar caps and blast-radius checks; approval-required fixes carry "verification criteria". Detector rules and auto-fix paths are pre-authored by Omnitrace. No per-Run human-approved done clause is described.
- Records: "Action ledger", "Verification records". The docs say it "records the policy, the action, the tool response, and the verification outcome". The tool response is recorded, which implies the ledger entry completes after the call. No journal-before-call is described.
- Verdict vocabulary seen: VERIFIED, APPLIED, INVESTIGATING (action cards), REGRESSED. Findings also show a numeric confidence ("Confidence 0.95"). Behavior on a failed or missing read-back (Unknown, pass, fail) is not described anywhere I read.

**7-part, docs only (nothing live):** all seven are COULD-NOT-VERIFY. Nearest claimed behavior: read-back (4), approval and autonomy gates (3), an action ledger (6). Per your rule, no marketing claim is upgraded to CONFIRMED.

**Part 2 claim check:** the homepage wording behind "Read-back proof" is real as quoted. What the pages add: Databricks-only destinations today, the table-maintenance read is a later telemetry comparison, scores appear on findings, no Unknown behavior is documented. Live read-back behavior stays COULD-NOT-VERIFY.

**To get past the gate you would have to do one of these (your call, in Main):** request the pilot through Contact sales under your own email and real Databricks access; or sign up for Databricks Free Edition yourself and confirm Omnitrace accepts it (ask them directly); or leave it docs-only. Do not paste any Databricks password or token in chat.

---

## 5. tau-bench / tau2-bench

**Verdict: CONFIRMED** (the skeptic finding). State read: yes. Three-valued verdict: no. Production gateway: no.

| Field | Value |
|---|---|
| Repo | `github.com/sierra-research/tau2-bench`, 347 commits |
| Commit tested | `c06b07dd7c4d4ec61ba6ff9bcdf0b15dd7ef36d4`, 2026-11-10T12:51:08-08:00 |
| Package | `tau2` 2.0.0, Python >=3.12,<3.14, installed with uv (Python 3.12.3) |
| Date checked | 2026-11-17T04:16Z to 04:20Z on the sandbox clock (session date 2026-11-16) |

### What "adapter" meant

Nothing in the repo is named an adapter for this purpose. The word appears for leaderboard-submission preparation and for realtime voice providers. I ran the evaluation entry point, `evaluate_simulation()`, which both `tau2 run` (`runner/simulation.py`) and `tau2 evaluate-trajs` (`scripts/evaluate_trajectories.py`) call. **No agent or user-simulator LLM ran** (that needs keys). I fed it trajectories I built by executing tool calls in the benchmark's own `mock` domain environment. Retail, airline and telecom were not run.

### How the verdict is computed (code, then live)

- `EnvironmentEvaluator` builds a **predicted** environment by replaying the logged messages into a fresh environment (`set_state(message_history=...)`), and a **gold** environment from the task's initial history plus its golden actions.
- It hashes the agent DB and the user DB of both (`get_db_hash()`) and compares. Equal is `db_reward` 1.0, otherwise 0.0. Environment assertions are 1.0 or 0.0. The final reward is the product of the components in the task's `reward_basis`.
- The "independent read" is a **replay of the log into a simulated DB**, not a read of an external system. No settle delay exists.
- Tool messages carry `execution_status` `executed` or `rejected`. Replay skips only explicit pre-execution rejections; a tool that errors after writing still counts as executed (repo test passes). Closest thing in the set to attempted-versus-landed, but deterministic, not an Unknown.
- `get_db_hash()` returns `None` when a domain has no DB, and two `None` values compare equal.

### Excerpts (task `create_task_1_with_env_assertions`, basis DB + ENV_ASSERTION)

```
E1 correct effect                              reward 1.0  db_match true   breakdown {DB 1.0, ENV_ASSERTION 1.0}
E2 wrong effect (altered argument)             reward 0.0  db_match false  breakdown {DB 0.0, ENV_ASSERTION 1.0}
E3 no effect, agent only claims success        evaluator RAISED ValueError("Task task_2 not found") from the env-assertion read; no reward returned
E3b same, DB-only basis                        reward 0.0  db_match false
E4 correct effect, run ended max_steps         reward 0.0  note "Simulation terminated prematurely"   (effect landed, scored 0.0)
E5 correct effect, run ended infrastructure_error  reward 0.0 same note
E6 write attempted, recorded as rejected-before-execution   evaluator RAISED the same ValueError
E7 task with no evaluation criteria            reward 1.0  note "No evaluation criteria"
replay hashes (first 10 chars): gold 3b82583d5c | predicted correct 3b82583d5c | wrong 39875e084a | no-op 107f83a70b
reward type: float, values seen only 1.0 and 0.0
```

- **Unknown vocabulary:** none in the reward path. The only hits are an "Unknown evaluation type" error string and an error-source field ("user", "agent", "unknown"). Termination reasons (`max_steps`, `timeout`, `infrastructure_error`, ...) all collapse to 0.0.
- **Journal before call:** none. `_execute_tool_calls` runs `environment.get_response()` in process. The trajectory is an in-memory list. `runner/checkpoint.py` saves finished simulations (`results.json`). From code reading, not instrumented.
- **LLM judges exist** but did not run here: the default `COMMUNICATE` scorer is semantic (an LLM judge), `NL_ASSERTION` uses an LLM, and `tau2 review` and `tau2 judges` run LLM reviews. They apply only when those reward bases are present.
- **Repo's own offline tests** (`tests/test_environment.py`, `tests/test_evaluate_trajectories.py`): 29 passed.
- `runner/simulation.py` calls `evaluate_simulation()` with no local try/except. Batch-layer handling of an evaluator exception was not tested.

### Pass / fail

- **Expected** (state read yes, tri-state no, production gateway no): **matches.**
- **Iris 7-part:** 0 of 7. Nearest: per-task success criteria exist before the run, and a replay-and-hash state check.

### What remains unresolved

- A live agent plus user-simulator run (needs LLM keys). The original `tau-bench` v1 repo was not run, only tau2. Other domains. Batch-layer behavior when the evaluator raises.

---

## Synthesis

**Does "none found in ~20" survive live testing?** Yes, with a tighter footing. Four candidates were tested live (SafeNode, MCPKernel, mcp-airlock, tau2-bench). None does claim intake, per-Run human-approved done clauses, a settle-aware independent read-back, a three-valued verdict without scores, a committed journal before egress, or stops a Run only on Incorrect. Omnitrace is untested, so the claim cannot go stronger than "none found in ~20 candidates", and Omnitrace is the one open item that could change it.

**What changed from the Part 2 report**

| Item | Part 2 / skeptic said | Live result |
|---|---|---|
| SafeNode spawn and replace | COULD-NOT-VERIFY; Glama says echo-only | **CONFIRMED.** Spawn code and a live spawn from a one-entry client config. "Echo-only" is the bundled demo config |
| SafeNode, extra facts | not covered | Policy is evaluated in a hosted API per call (args leave the machine, scrubbed by default). Local decision log is best-effort. README's `raise` claim is **CONTRADICTED** |
| MCPKernel `:8000/mcp` | COULD-NOT-VERIFY port, path and flow | **CONFIRMED.** Port is a flag. `/mcp` redirects to `/mcp/`, session-based. Flow is pre-call policy, forward, post-call taint, then audit |
| MCPKernel, extra facts | "emphasizes post-execution taint" | Confirmed for results. Argument taint arrives after policy, so taint rules cannot gate. `sandbox` action blocks. Denied calls unlogged. YAML `policy_paths` crashes startup |
| mcp-airlock capability lease | no primary source located | **CONFIRMED** in code and live. Not a gateway. Self-issued leases. Schema forbids the lease fields |
| Omnitrace "Read-back proof" | CLAIMED YES-READ, docs unread | **Still COULD-NOT-VERIFY** |
| tau2-bench | skeptic: state read yes, binary, benchmark only | **CONFIRMED**, plus: no criteria scores 1.0, early end scores 0.0, evaluator can raise |

**Cross-cutting, seen live:**

- **Landed effect, error reported, no Unknown:** SafeNode S7, MCPKernel B, and MCPKernel A1 unprompted. This is direct support for the Iris rule that a timeout after a commit is Unknown and must be verified before any retry.
- **Blocked and failed results look like success:** MCPKernel returns blocked and upstream-error text with `isError=false`. A client keyed on the flag misreads both.
- **Closest to journal-first:** SafeNode's synchronous pre-forward line. Nothing commits before egress.

**Observations bearing on filed Iris problems (nothing built):**

- *MCP churn (problem 4):* SafeNode and MCPKernel negotiated 2025-11-25 through SDK 1.30.0. mcp-airlock hard-codes 2025-03-26. MCPKernel's HTTP endpoint is session-based (`Missing session ID`, `mcp-session-id` header). The default `pip install mcp` pulled 2.3.0, where `FastMCP` is renamed `MCPServer`; MCPKernel pins below 2. I did not test anything against the 2026-07-28 revision.
- *Windows (problem 3):* nothing tested; Linux sandbox only.

**Still COULD-NOT-VERIFY:** Omnitrace entirely; SafeNode's hosted engine; MCPKernel sandbox backends, signing, auth, DEE; mcp-airlock success path; tau2-bench with a live agent and tau-bench v1; everything on Windows; Claude Desktop itself.

---

## Deviations from the filed prompt, and limits

1. **Claude Desktop not available.** A scripted MCP client read a Claude Desktop style config.
2. **SafeNode evaluator.** Two stand-ins: an unreachable local port (fail-closed) and a local stub that I wrote (S2, S3, S7). The stub's decisions are mine. SafeNode's real engine was not exercised.
3. **MCPKernel.** Policy path passed by environment variable because of the YAML startup crash. Run A1 (typed upstream) and A2 (untyped upstream) are both reported.
4. **mcp-airlock observer.** The server was launched through a wrapper that records the ledger line count when name resolution happens inside the tool. The product's source was not modified.
5. **Omnitrace not tested.** Reasons in section 4. I continued to tau2-bench because it is independent; say if you wanted a hard stop at the first blocked candidate.
6. **tau2-bench:** no "adapter" found; evaluator run directly on hand-built mock-domain trajectories; no LLM.
7. **Sandbox pauses.** One pause killed my stub evaluator, so the first S3 and S7 runs hit "fetch failed" and were discarded and re-run. The clock crossed midnight UTC.
8. **Repos untouched.** `git status` was clean in all three clones. A scan of my fixtures for key and token patterns found nothing.
9. **Report location:** outputs folder, per the latest instruction (the filed prompt names the repo worktree). Not pushed.
