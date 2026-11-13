# Deep-research report — all topics, one job

Date: 2026-11-13. Method: `/deep-research` multi-agent sweep, 8 topics in
parallel plus a synthesis pass, sources cross-checked, no code copied.
Unverified items are marked unresolved in each section — treat those as
leads to re-check, not facts.

Base: `main` at `747414b` plus the `.gitignore` cleanup commit on top
(see git log at commit time). Suite: 60/60 green at report time.

Headline across all topics: observability is commoditised
(traces/evals); the open gap a local Windows tool can own is
governance-enforcement at a local gateway — steer/kill, hard spend caps,
identity, taint, memory audit — plus the Bridge pattern and a live
monitoring station that reuse the existing proxy/API instead of
duplicating them.

---

## 1. Iris product search — agent observability and governance

Headline: observability is commoditised (traces/evals);
governance-enforcement at a local gateway — steer/kill, hard spend caps,
identity, taint, memory audit — is the open gap a local Windows .exe
can own.

Findings:

- WATCH (table stakes, commoditised): trace tree/timeline, session/user
  tracking, agent graphs, token+cost+latency per span, OTel ingestion.
  LangSmith, Langfuse, Arize Phoenix, AgentOps all do this. No
  differentiation in another trace viewer.
- VERIFY: evals/LLM-as-judge, datasets, annotation queues exist in
  Langfuse/LangSmith/Braintrust/Phoenix but are tied to SDK
  instrumentation and cloud. A local proxy seeing only wire traffic
  cannot judge semantic correctness — the gap is verifying claims vs
  actual tool calls/destinations, not output quality scores.
- STEER (biggest unmet need): human approval gates, interrupt/resume,
  kill-switch/circuit-breaker, autonomy budgets (write/execute/commit
  limits). Controls must live OUTSIDE the agent loop at the gateway.
  Most tools observe; they do not block/pause/kill. A local .exe as
  gateway is the enforcement point.
- METER + SPEND CAPS: meter from provider-reported usage only, never
  invented ($0.0000 if unreported). LiteLLM does per-key budgets but
  accounting is largely post-call; pre-call hard caps (warn ~80%, block
  100%, per-run/day/month, per-destination/agent) are rarer. Automated
  pricing: pull official provider price lists, version them, show price
  source + date per line item; never hard-code stale prices.
- SHIELD: allowlist/blocklist at proxy (403 HTTP, no tunnel on CONNECT),
  rate-limit 429 with recovery, redaction (never log auth headers or
  bodies), prompt-injection/taint flags. OWASP LLM01 + LLM06 + LLM10 are
  the design checklist. Policy enforcement, not ML-detection promises.
- REPLAY: AgentOps time-travel is closest; Langfuse/LangSmith replay is
  re-inspection, not deterministic re-execution. Honest local feature:
  re-show the exact metadata timeline + what was blocked/allowed, plus
  safe re-run in dry-run/block mode — never claim identical
  re-execution.
- IDENTITY/PASSPORT: per-agent non-human identity (id, owner, purpose,
  scoped expiring credential, provenance chain human -> agent -> tool).
  Gap: existing offers are enterprise/cloud; no local plain-language
  passport a solo Windows user can issue/revoke and attach to every
  proxy row (trace_id + agent_id + owner).
- MEMORY AUDIT: memory writes with no provenance/integrity are flagged as
  a top governance risk; need append-only audit (source, taint, author,
  time), poisoning scan, delete/rollback per entry. Almost no
  observability tool audits memory contents.
- INJECTION/TAINT: taint-track external content (web, file, MCP tool
  output, retrieved docs); if tainted content reaches a tool call,
  memory write, or high-impact action, flag/block. Deterministic taint
  labels beat probabilistic detectors for a local-tool claim.
- COMPLIANCE PACK: one-click evidence pack mapping proxy logs to EU AI
  Act Art.12, SOC2, ISO 27001/42001, NIST AI RMF. Local differentiator:
  plain-language export (PDF/MD) with hash-chained rows, retention, no
  bodies/secrets.
- SWARM MAP: multi-agent visualisation exists only fragmented
  (AgentOps fleets, per-trace agent graphs). Gap: live map across
  agents/processes on one Windows machine — who talked to whom, which
  destination, cost, blocked edges — from proxy metadata only, no SDK.
- TLS: local proxy must NOT MITM/decrypt. CONNECT = raw byte relay,
  count bytes, one metadata row per tunnel. Sees
  destination/size/timing, not plaintext — that honesty is the selling
  point.
- MCP: spec standardises Host/Client/Server, Tools/Resources/Prompts
  over JSON-RPC 2.0 but explicitly does NOT enforce security; tools =
  arbitrary code execution, consent required. Gap: local MCP gateway
  with server/tool inventory, tool-description pinning (rug-pull
  detection), per-tool consent, metadata-only call log.
- TCP/UDP + GATEWAY: LLM gateways cover HTTP LLM APIs only. Generic
  TCP/UDP agent traffic is unobserved by all of them. Scoped
  differentiator: HTTP forward proxy + CONNECT + (future) TCP relay with
  byte counts; log UDP as flows, never promise request/response
  semantics.
- PRICED COST / AUTOMATED PRICING: LangSmith ~$39/seat + trace overage;
  Langfuse OSS self-host free, cloud $29–2499. Iris wedge: one-time or
  low flat local licence, no per-seat/per-trace meter, data stays on
  machine — but never invent competitor totals or provider token prices;
  show a dated source per price.
- POSITIONING no one else does: (1) no SDK/code change — point the agent
  at the local proxy, (2) plain English (Watch/Steer/Shield, not
  spans/OTel), (3) enforcement not just charts (pause/block/kill, spend
  hard-stop), (4) all data local SQLite, loopback only, (5) works across
  any agent using HTTP/CONNECT/MCP regardless of framework.

Load-bearing: steer (pause/approve/kill + autonomy budget at the proxy,
outside the agent loop); Shield enforcement (allowlist 403/no-tunnel,
rate-limit 429 + recovery, outcome reconciliation
allowed+blocked+rate_limited+other = total); meter with pre-call hard
spend caps using provider-reported usage only; per-agent
Identity/Passport on every metadata row; injection/taint + memory audit;
MCP gateway (inventory, pinning, consent, metadata-only log); no-MITM
TLS honesty + local-only/SQLite/loopback trust claim; Swarm Map from
metadata only; compliance pack as hash-chained plain-language export.

Skippable: another SDK/framework integration or OTel span viewer;
LLM-as-judge suites, prompt playgrounds, dataset management; cloud
multi-tenant RBAC/SSO, long retention hosting; probabilistic
injection-ML-detector claims; generic UDP deep inspection and
deterministic re-execution promises; per-seat/per-trace pricing mimicry.

Proprietary / cannot copy: LangSmith/Langfuse trace UI, evaluator
prompts, judge rubrics, pricing-page copy — build metadata-only views
from the repo's own SQLite schema. Do not reuse LiteLLM/Helicone gateway
code or present their price tables as own — build a versioned catalogue
from official provider pages with attribution + date. Do not clone
AgentOps time-travel or Phoenix OTel UI. MCP is an open spec (implement
freely) but do not copy sample server code verbatim without a licence
check. No TLS MITM/decryption, no body/secret logging — legal, trust,
and repo-contract boundary.

Sources:

- <https://www.langchain.com/pricing>
- <https://langfuse.com/pricing>
- <https://langfuse.com/docs>
- <https://modelcontextprotocol.io/specification/2025-11-25>
- <https://aidren.co.uk/learn/owasp-top-10-for-llm-applications.html>
- <https://www.computer.org/publications/tech-news/trends/autonomy-budgets-for-ai-agents>
- <https://10decoders.com/blog/ai-agent-circuit-breaker-kill-switch-gap-2026>
- <https://www.llmbrake.com/blog/per-user-llm-budgets-compared>
- <https://www.ovaledge.com/blog/agent-memory-governance-framework>
- <https://www.nhigovernance.com/glossary/ai-agent-identity.html>

Unresolved: OWASP primary PDFs not fetched directly (3 secondary sources
only); AgentOps/Arize exact current pricing unverified on official pages;
no official OpenAI/Anthropic price pages fetched (pricing-automation
design is recommendation only); no competitor found for generic TCP/UDP
agent observability (absence-of-evidence, not proof); swarm-map and
memory-audit depth assessed from comparisons, not hands-on trials;
ServiceNow AI Passport / IBM Agent Identity dates from secondary news,
not vendor pages.

---

## 2. Gateway — can a local client like Iris function as one?

Headline: gateway = proxy + per-consumer policy; Iris is a launcher
(control plane), not a gateway — it can bundle one, but should keep the
gateway as a separate fail-closed data-plane process.

Findings:

- Verdict: different job today, enmeshable tomorrow. Iris launches and
  monitors proxy.py and the API as subprocesses; it contains no
  forwarding, routing, auth, or policy code. A client becomes a gateway
  only when traffic it does not originate is forced through it and it
  decides admit/route/transform for others. Hosting that in-process
  inherits gateway duties — fail-closed policy, credential custody,
  audit — and a GUI close turns into a traffic outage. Industry pattern
  is bundle-but-separate processes.
- Proxy vs gateway line: a proxy forwards and optimises at
  connection/request level; a gateway is a proxy PLUS per-consumer
  product policy — identity/authn/authz, quotas per key/team,
  request/response transformation, credential brokering, catalog,
  metering/audit. People expect a proxy to be transparent and fast; they
  expect a gateway to be opinionated and accountable.
- Routing expectations by gateway type: API gateways (Kong/Envoy
  Gateway/NGINX) route L7 host/path/header/JWT claims with per-route
  filter chains. LLM gateways (LiteLLM/Portkey/OpenRouter) do
  model-alias routing, token-aware limits (TPM/RPM, $ budgets per
  virtual key/team), fallbacks/retries, semantic caching — and must
  parse bodies to count tokens. MCP gateways route by server/tool, not
  URL: aggregate many MCP servers behind one endpoint, curate tools/list
  per caller, enforce per-tool allow/block on tools/call, inject
  per-user credentials, optionally sandbox servers. TCP/UDP gateways are
  L4 — IP/port/protocol/identity only, no payload inspection.
- Auth/policy/per-tool: gateway auth is centralised — never distribute
  provider keys; issue virtual/scoped keys with allowed models and
  max-budget/RPM/TPM caps. Granularity escalates API (per route/consumer)
  -> LLM (per key/team/model/budget) -> MCP (per user/group x server x
  tool x call). This repo's allowlist + 429 is gateway-embryo policy:
  destination-level, no identity or tool level, no credential brokering.
- Enmeshing in one app: technically yes and common (one binary serves
  both roles — role is topological, not technological), but keep planes
  separable: control plane (Iris UI/config/catalog), data plane (proxy
  forwarding), policy plane (allow/block/budget decisions) with the data
  plane fail-closed when policy is unavailable. Never put policy inside
  the byte relay: CONNECT tunnels must stay opaque/count-only per the
  no-MITM contract; per-tool or per-token decisions belong on the
  HTTP/MCP/LLM legs where the protocol is already terminated and
  visible.

Load-bearing: the gateway definition above (sourced from Kong/NGINX
comparisons, API gateway definitions, LiteLLM/MCP gateway docs,
cross-checked against Cloudflare's L4–L7 model). Iris classification
rests on directly inspected local code: iris.py only launches/monitors
subprocesses; all forwarding/policy lives in proxy.py.

Skippable for v1: full virtual-key issuance service, per-team catalog UI,
multi-protocol termination beyond HTTP — add the policy layer in front
of forwarding first.

Proprietary / cannot copy: Kong/Envoy/NGINX code, LiteLLM proxy code,
vendor gateway UIs and docs copy — implement own policy layer; MCP is an
open spec. Never terminate/decrypt CONNECT tunnels to inspect payloads.

Sources:

- <https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-wan/zero-trust/security-services/>
- <https://docs.docker.com/reference/cli/docker/mcp/gateway/run/>
- <https://docs.litellm.ai/docs/proxy/architecture>
- <https://gateway.envoyproxy.io/latest/api/gateway_api/gateway/>
- <https://zuplo.com/learning-center/best-api-gateways-2026>
- <https://www.docker.com/blog/mcp-horror-stories-github-prompt-injection/>

Unresolved: Iris assumed to be this workspace's iris.py launcher
(inspected directly); if a different Iris was meant, the verdict still
holds for a local client. Recommendation for this repo: keep Iris as
launcher + dashboard shell; add gateway features (per-tool allow/block,
virtual keys) in proxy.py/api.py as a policy layer in front of
forwarding, not inside the iris.py GUI process and not inside CONNECT.

---

## 3. Tools — is Iris good on tools as-is, or can it enmesh more?

Headline: Iris is a solid destination-level proxy, not yet a
tool-governance layer — enmesh a tool-aware gateway inside its
trace/allowlist spine; do not make the tunnel parse tools.

Findings:

- Verdict: good as-is at network governance, NOT tool governance. Keep
  it as the outer ring; enmesh a tool-aware layer inside rather than
  teaching the CONNECT proxy to parse tools — that would break its
  metadata-only, no-MITM contract.
- Per-tool policy and kill (highest value): add a loopback tool/MCP
  gateway or agent-side middleware where tool_name is visible in
  plaintext — policy table keyed (agent_id, tool_name) to
  allow/deny/require_approval, argument shape checks on hashes/metadata
  (never values), risk tiers (read vs write vs irreversible), per-tool
  rate + call-count caps, scoped short-lived credentials per tool. Kill
  in 3 layers: disable one tool, freeze one agent/trace, global stop
  (today's process kill becomes layer 3 only). Any runtime kill/policy
  control contradicts api.py's read-only contract and needs explicit
  human approval before building.
- Tool-call truth: add outcome `unknown` distinct from failure for
  timeout-after-send, resets, and 502/504 — and extend reconciliation
  (allowed + blocked + rate_limited + unknown + other = total). Before
  retrying a write: verify-before-retry — persist operation id,
  idempotency key, trace_id, tool, payload hash BEFORE dispatch, reuse
  the same key on retry, query status or read back first; blind
  auto-retry only for pre-send errors and idempotent reads.
- MCP tools: inventory servers + tools via tools/list, pin tool
  name+inputSchema hash at approval, alarm/re-approve on
  tools/list_changed or hash change (rug-pull), treat descriptions and
  outputs as untrusted, log method + tool_name + isError + latency
  without arguments.
- Tool-call cost: keep "unknown, never invented"; extend the
  price-table pattern to per-(tool, destination) source-cited prices,
  attribute tokens/cost per tool + agent + trace, add per-tool /
  per-agent / per-trace call and dollar caps enforced pre-call (deny
  reason `budget_exceeded`, logged, $0 forwarded) with ~80% alerts.
  Swarm loops are the main burn risk the per-destination rate limit only
  partly bounds.
- Swarm tool use (partial today): trace_id + task numbers already stitch
  legs under one trace — good audit spine. Missing: authenticated agent
  identity (X-Strategy is unauthenticated bookkeeping, not auth),
  role-based per-agent tool policy, delegation/sub-budgets, fan-out and
  parallel-call caps, aggregate swarm budget/kill.
- What people look for (cross-source checklist): deny-by-default
  per-tool allowlist; least-privilege scoped creds; human approval for
  irreversible/high-impact; deterministic pre-call policy outside the
  model; reconciling audit trail; per-tool + per-agent budgets/rates with
  hard stops; instant layered kill switch; timeout-as-unknown +
  idempotency + verify-before-retry; MCP inventory/pinning/change
  detection; injection/poisoning defence; per-tool latency/error/cost
  observability. Iris today ticks the network-level items and none of
  the tool-semantic ones — structurally, because at CONNECT/HTTP layer
  it cannot see them.

Load-bearing: `is_allowed`/`check_rate` are destination-keyed only; the
attempts schema has no tool/agent/idempotency fields; timeouts map to
failure/error with outcome allowed, never unknown; kill is
terminate-both-processes and the API is read-only; cost is
unknown-not-guessed with a wasted rollup but no budget enforcement; MCP
tools/list + tools/call semantics are invisible inside CONNECT.

Skippable: teaching the proxy to parse bodies/TLS; probabilistic tool
analyser claims; full parallel-call orchestration v1.

---

## 4. Hostile agentic swarms — detection

Headline: hostile agentic swarms are detected at group level —
synchrony, shared artifacts/infrastructure, capability spread and Sybil
fingerprints — never from one agent or one signal; OWASP ASI07/ASI10,
MITRE ATLAS, Science, Talos and botnet research agree coordination must
be proven against a legitimate-automation baseline.

Findings:

- How to detect (population, not single-agent): build a time-ordered
  graph whose nodes are agents/identities/accounts/hosts and whose edges
  are messages, shared artifacts (files, cache keys, repos, boards),
  shared infrastructure, and same-capability adoption. Look for
  correlation in time + cause: many agents exploring in parallel then
  converging, one agent's discovery/tool/capability suddenly appearing
  in others, repeated touching of the same shared resource just before
  the group changes behaviour, persistent subgroups with bridge or
  coordinator nodes. A single weird agent is an incident; synchronised,
  dividing-the-work behaviour across many is a swarm.
- Signals ranked: (1) Coordination — near-simultaneous starts/bursts,
  parallel probing then convergence, task-splitting (one recons, one
  exploits, one exfiltrates/posts). (2) Propagation — same prompt, tool,
  skill, error string, or capability spreading agent-to-agent. (3) Hidden
  channels — coordination via writable cache, filenames, shared
  docs/repos instead of a visible message bus, or spoofed/replayed
  inter-agent messages (OWASP ASI07). (4) Boundary pressure —
  coordinated probing of identity, policy, rate-limit and budget edges,
  spawning sub-agents without per-child permission/budget. (5) Classic
  botnet network signals still apply: regular beaconing, DGA-like DNS,
  low-TTL/fast-flux, non-browser user-agents, WAF/SQLi spikes
  (Talos/Vectra). (6) Sybil signals: many "independent" identities
  sharing device/TLS/funding/payment/infra/timing fingerprints.
- Normal vs rogue: normal means a known orchestrator and owner, signed
  separate identity and least-privilege credentials per agent, fixed or
  declared roles, predictable tools/destinations/volume, budgets and
  kill-switch, signed immutable logs the agent cannot edit, human
  approval for high-impact actions, and bursts explained by CI/deploy/
  support schedules. Rogue means an unknown or impersonated
  orchestrator, trusted unauthenticated peer instructions, goal/scope
  drift, concealment (editing/disabling logs, side channels),
  persistence beyond intended lifetime, uncontrolled spawning,
  disposable short-lived agents, capability sharing outside the trust
  zone, and individually harmless actions that only make sense as a group
  objective (OWASP ASI10 Rogue Agents).
- Fingerprinting: per-agent behavioural fingerprint = tool-call mix and
  order, destinations, timing/latency, volume, vocabulary, approval
  patterns — baseline it and alert on drift. Identity fingerprint =
  cryptographic agent identity, signed messages, mutual authentication,
  attested registry, so "same name, different behaviour" exposes
  impersonation. Network fingerprint = TLS/JA3, user-agent, DNS/beacon
  periodicity. Group fingerprint = graph clustering on shared
  infra/funding/artifacts/timing — this catches Sybils even when each
  fake identity looks unique. Fingerprinting identifies sameness and
  drift; it does not by itself prove intent.
- What a Shield / Swarm-map looks for first ("Shield"/"Swarm map" are
  not standard framework names — treated as the defensive map): first
  identity and orchestration (owner, coordinator/bridge nodes, are peer
  messages authenticated?); second shared things (one artifact/cache/
  repo/credential touched by many agents before a joint shift); third
  loud early network tells (automated-traffic/WAF/SQLi spikes, DNS
  beaconing); fourth boundary and budget pressure plus drift from each
  agent's baseline. Only then label "rogue" — keep observed facts
  separate from inferred coordination and state uncertainty, because
  legit automation moves together and bursty humans look coordinated.
- Plain-words value: a hostile swarm is a fake crowd — one hidden
  operator pretending to be many people or many helpful robots.
  Detecting it stops factories of fake agreement (astroturfed politics,
  rigged reviews/votes), fast group cyberattacks that probe from a
  hundred directions at once, and scams no single fake account could pull
  off. Done well, it protects real voices from being drowned out and
  lets good agent teams keep working. Done badly (single-signal bans),
  it silences genuine crowds — so evidence must be group-level,
  multi-signal, and reviewable.

Load-bearing: no single signal proves malicious coordination —
temporal/causal context, comparison with legitimate orchestration, and
explicit uncertainty are required; modern swarms coordinate without a
message bus via shared artifacts/cache/repos/side-effects; human-level
mimicry and heterogeneous rhythms defeat old synchrony detectors, so
graph, propagation, and boundary-pressure signals are the durable layer.

Skippable: single-signal detectors (synchrony-only, copy-paste-only);
per-agent anomaly scores presented as swarm verdicts.

Proprietary / cannot copy: vendor threat-intel feeds and write-ups
(paraphrase, don't reproduce); Talos wording via summaries only.

Sources:

- <https://arxiv.org/html/2506.06299v4> (Science 2026, DOI 10.1126/science.adz1697)
- <https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/>
- <https://atlas.mitre.org/>
- <https://www.inwom.com/insights/ai-agent-swarm-attacks>
- <https://www.vectra.ai/topics/botnet-detection-techniques>
- <https://intel.threadlinqs.com/threat/TL-2026-3163>

Unresolved: MITRE ATLAS homepage is JS-rendered (technique-level claims
corroborated via OWASP/Inwom references, not quoted from atlas.mitre.org
directly); "Shield"/"Swarm map" interpretation is inference, not sourced
terminology; Talos primary post via two summaries, and no complete
confirmed swarm attack chain is yet documented — real-world evidence
remains partly emerging, not mature forensic record.

---

## 5. PyCharm Professional internals, clean-room

Headline: PyCharm Pro = IntelliJ Platform (open-source JVM host, PSI +
indexes + VFS + services/extensions) + closed Python plugin (Pythonid)
adding the interpreter model, debugpy/pydevd debugger, run/test configs,
and remote interpreters; load-bearing for agent workflows is PSI/index,
the interpreter/run-config abstraction, and the debugger protocol — not
UI chrome.

Findings:

- Architecture (public): the IntelliJ Platform is a component-driven
  cross-platform JVM application host. Layers bottom-up: VFS (cached
  file mirror) + Document/Editor model -> PSI (Program Structure
  Interface: syntactic + semantic model) -> Indexes (File-Based + Stub)
  -> language services (completion, navigation, inspections,
  refactorings, find-usages) -> UI. Project model (modules, SDKs,
  libraries, facets) sits alongside. Threading: single EDT + background
  threads with an application-wide read-write lock; coroutine dispatchers
  since 2024.1.
- Editor: full-text editor with highlighting, folding, completion,
  multiple carets. Access via FileEditorManager and PSI-linked editors;
  Documents are the mutable text layer under PSI files. Python specifics
  (injections, inference display, docstring rendering) live in the
  closed Python plugin.
- Indexing / PSI (core differentiator): PSI parses each file to a tree;
  the stub tree is a serialized subset with only externally visible
  declarations. File-Based Indexes map key -> files; Stub Indexes map
  key -> PSI elements. Indexes enable symbol search, completion,
  find-usages, and navigation without reparsing the repo. During indexing
  the IDE enters Dumb Mode: only index-independent features work. The
  index binary format is undocumented implementation detail.
- Debugger: PyCharm uses debugpy as the default debugger for Python 3.9+
  on local and WSL interpreters, based on the Debug Adapter Protocol;
  legacy pydevd remains selectable. Gaps for debugpy: remote targets,
  attach-to-process, doctest/Scrapy/remote Jupyter/Django manage tasks.
  The platform provides language-agnostic breakpoint/call-stack/watch
  infrastructure; Python bridging is Python-plugin proprietary.
- Python interpreter handling: at least one interpreter required. Model:
  base interpreter + venv layers (system, Virtualenv, pipenv, Poetry,
  uv, hatch, conda). Pro adds remote interpreters (SSH, Docker, Docker
  Compose, WSL) plus deployed "helpers" for remote packaging/debugger/
  tests. Per-project SDK + module SDKs; status-bar widget switches envs.
- Git integration: platform VCS abstraction with Git as a bundled plugin
  — clone, branches, sync, commit+push, merge/rebase/cherry-pick,
  conflict resolver, changelists, shelf/stash, log/annotate, interactive
  history edit, GitHub PR / GitLab MR review. A GUI over git operations
  + diff/merge editor; no proprietary VCS engine.
- Run/test configs: named sets of startup properties (what to execute +
  parameters/environment). Temporary (auto-created, max 5 kept) vs
  permanent (saved as XML under `.idea/`, shareable in VCS). Created
  from templates (Python script, pytest/unittest, Django, remote…); the
  same config drives Run, Debug, and test execution.
- Plugin system: everything is a plugin — plugin.xml descriptor +
  Actions, Extensions, Services (app/project/module singletons),
  Listeners, own extension points. Module dependencies
  (`com.intellij.modules.platform`, `PythonCore` CE vs `Pythonid` Pro).
  Distribution via JetBrains Marketplace; per-plugin classloaders.
- Pro vs Community (unified installer since 2025.1, Pro by
  subscription): Pro adds remote interpreters, Django/Flask/FastAPI,
  database tools, scientific tools, deployment, web extras. The platform
  itself is Apache-2.0 open source; the Pro Python plugin and some Pro
  features remain closed.

Load-bearing for agent workflows: PSI + Stub/File indexes (replicate via
LSP/AST + index, e.g. Jedi/pyright/Rope or tree-sitter + ctags, not text
grep); interpreter-as-SDK abstraction (per-project resolved env driving
run/debug/test/package consistently); run/debug configuration as a named,
persisted, templated launch spec; debugger via public DAP/debugpy;
service/extension-point architecture for long-lived indexed backends;
VFS + Document consistency under external changes (agent edits on disk
must invalidate caches).

Skippable: Swing/JVM UI toolkit, themes, editor rendering; database/SQL,
Django extras, scientific viewers, deployment dialogs; marketplace
distribution and classloader isolation (unless building IntelliJ plugins
themselves); GUI Git UX (agents use git CLI); remote split-mode;
proprietary inspection/quick-fix catalog breadth (cover via ruff/pyflakes
instead).

Proprietary / cannot copy: Pythonid plugin source and Python-specific
PSI/type-inference internals; index binary on-disk format (explicitly
undocumented, changes without notice); pydevd internals and
beyond-public-DAP debugger extensions (use public debugpy/DAP spec);
remote helpers binaries, deployment/sync protocols, Pro
database/scientific/Django implementations, licensing/activation;
inspection algorithms and ML completion ranking (describe behaviour;
implement with public tooling).

Sources:

- <https://plugins.jetbrains.com/docs/intellij/intellij-platform.html>
- <https://plugins.jetbrains.com/docs/intellij/psi.html>
- <https://plugins.jetbrains.com/docs/intellij/indexing-and-psi-stubs.html>
- <https://plugins.jetbrains.com/docs/intellij/plugin-structure.html>
- <https://plugins.jetbrains.com/docs/intellij/plugin-services.html>
- <https://plugins.jetbrains.com/docs/intellij/threading-model.html>
- <https://plugins.jetbrains.com/docs/intellij/editors.html>
- <https://www.jetbrains.com/help/pycharm/configuring-python-interpreter.html>
- <https://www.jetbrains.com/help/pycharm/debugging-code.html>
- <https://www.jetbrains.com/help/pycharm/run-debug-configuration.html>
- <https://www.jetbrains.com/help/pycharm/using-git-integration.html>

Unresolved: closed-source type inference, remote helpers protocol, and
Pro-only internals have no public spec (clean-room limited to Help
docs); index format internals inferred from SDK APIs only; 2025.1
unified-installer feature gating not fully enumerated — verify per
version; pytest/unittest template specifics not separately inspected
(test-runner page moved).

---

## 6. IDE own Co-Work functionalities, clean-room

Headline: copy the 6 functions (task loop, Projects, scheduler, MCP
connectors/plugins, 3 permission modes, artifact delivery) — build
local-first, single-agent, markdown-memory, not an embedded Cowork
clone.

Findings:

- Function map (all vendors converge): (1) Multi-step task = goal ->
  visible plan/subtasks -> tool loop (files/shell/browser/connectors) ->
  steer/cancel mid-run -> optionally parallel sub-agents/worktrees ->
  summary. (2) Project = named workspace binding {root folders/files,
  instructions file, memory, scheduled tasks, connector grants}.
  (3) Scheduled = {project, prompt/skill, cadence, run-location,
  permission profile} -> unattended fresh run -> inbox/triage
  (empty = auto-archived). (4) Connectors/plugins = MCP servers (open
  protocol) for external apps + plugin bundle {instructions/skills,
  connector configs, sub-agent defs, hooks}. (5) Permissions = the
  3-way spectrum everywhere: Ask-me (Manual/default), Auto-review
  (allowlist + sandbox + classifier for the rest), YOLO (Skip/Run
  Everything/full-access) + orthogonal sandbox (what/where it CAN do vs
  when it asks) + hard deny floor (protected paths, delete, deny rules
  survive even YOLO). (6) Delivery = run produces artifacts/diff in
  session, preview + download/open; for code a reviewable diff from an
  isolated worktree; run summary, never just chat text.
- Build from scratch, simpler, local-first (recommended): TaskRun as one
  durable record (goal, plan steps, status, tool log, artifacts)
  persisted in SQLite/JSON in the project; single agent loop first
  (defer parallel sub-agents — that parallelism is complexity, not the
  core value). Project = project folder + own instructions.md + memory.md
  (human-editable markdown; agent may propose appends approved in
  Ask/Auto modes; skip vector DB and opaque auto-memory initially).
  Scheduler = in-app cron table firing only while the IDE runs + missed-
  run catch-up (run once on next launch, marked missed) — skip cloud
  execution/sync v1. Connectors = MCP client only (one protocol,
  existing servers) with per-server + per-tool grants (Always / Needs
  approval / Blocked). Plugin = plain folder with manifest.json +
  instructions/skills + mcp.json fragment + optional hooks — no
  marketplace v1; install = copy folder + trust prompt.
- Permission design (exactly 3 modes): Ask me (default) — reads free,
  every write/shell/network/connector/delete prompts, "allow once /
  allow for this project" persists rules. Auto-review — project
  allowlist (commands, tools, domains) runs free, shell in workspace
  sandbox when possible, everything else to a cheap reviewer pass
  (second model call judging action vs goal); repeated denies fall back
  to Ask me. YOLO — no prompts BUT only selectable for an isolated
  workspace copy/worktree or container; a hard deny floor still applies
  (outside-workspace writes, secret files, permanent delete, network
  egress deny-list). Permanent delete asks in Ask/Auto in all products —
  keep that.
- Finished-file delivery (simpler): every run writes to
  project/outputs/<run-id>/; completion card lists artifacts with
  Preview/Download/Open-folder; for code tasks a unified diff view
  (Accept writes to real tree / Discard) because scheduled/YOLO runs
  execute in a scratch copy or worktree; scheduled runs land in an Inbox
  (findings vs no-findings auto-archived); run summary = steps done,
  files changed, tools used, anything blocked — never just chat text.

Load-bearing: the 6-function map above; markdown-first memory
(instructions.md + memory.md, human-editable); 3 permission modes with
sandbox orthogonality and a hard deny floor; worktree + diff-accept
delivery; in-app scheduler with inbox and missed-run policy.

Skippable v1: cloud runs, cross-device sync, parallel sub-agents,
marketplace, opaque auto-memory, full classifier infrastructure at
vendor scale; Cursor-style immediate-save-to-real-tree in Auto/YOLO;
session-only scheduling that dies silently.

Proprietary / do not copy: embedding Claude Cowork or any vendor agent
as a dependency (build own loop over the chosen model API); proprietary
cloud session sync, multi-surface handoff, parallel sub-agent
orchestration, plugin marketplace, auto-generated opaque memory, and
classifier infrastructure at full vendor scale; vendor UI copy, prompts,
and proprietary text — function only, clean-room.

Sources:

- <https://support.claude.com/en/articles/13345190-get-started-with-claude-cowork>
- <https://claude.com/product/cowork>
- <https://code.claude.com/docs/en/permission-modes>
- <https://code.claude.com/docs/en/permissions>
- <https://code.claude.com/docs/en/memory>
- <https://code.claude.com/docs/en/scheduled-tasks>
- <https://code.claude.com/docs/en/features-overview>
- <https://developers.openai.com/api/docs/guides/agents-api/sessions/approvals>
- <https://developers.openai.com/codex/app/automations>
- <https://cursor.com/docs/agent/security>
- <https://cursor.com/docs/enterprise/llm-safety-and-controls>
- <https://docs.windsurf.com/llms.txt>

Unresolved: Windsurf/Cascade is in transition (legacy/removed in Devin
Desktop) — treated as historical pattern only; Cursor run-modes page
direct fetch 404'd (corroborated via its security/enterprise pages +
search); Codex Automations page redirects to a navigation-heavy surface
(details corroborated across OpenAI-doc-quoting secondaries);
vendor naming/pricing/plan-gating changes fast — re-check mode
names/defaults per plan at build time.

---

## 7. Bridge — two agent sessions talking through GitHub

Headline: one append-only bridge file, strict turn-taking on separate
task branches, every handoff pinned to commit SHAs and the AGENTS.md
report format; GitHub is the transport/store, not a wake-up channel.

Findings:

- Pattern (file): create `docs/bridge.md` (docs/ is already the
  agent-handoff location per AGENTS.md). Append-only, never rewrite
  history in the file. Fixed sections: `## TASK <id>` (date, base SHA,
  from/to, turn owner, spec, in-scope files, acceptance criteria, exact
  test command); `## REPORT <id>` (result commit full SHA, files
  changed, test count, demo/report numbers, secrets result, still-open —
  mirrors the AGENTS.md report-back rule); `## ACK/REVIEW <id>`
  (approve/reject/questions). The turn token is the control: only the
  named turn owner may append/push; the other is read-only that round.
- Pattern (flow): (1) Sender: fetch, confirm clean scope and HEAD ==
  base SHA, append TASK, commit, push. (2) Human nudges the receiver
  session ("check bridge, task N") — no push notification reaches a
  closed/idle agent session. (3) Receiver: pull/rebase, verify base SHA
  and git status (scope commits by explicit file names, never
  `git add -A`). (4) Receiver works on branch `bridge/<id>`, implements,
  runs the full suite. (5) Receiver appends REPORT with result hash,
  pushes branch, optionally opens PR to main. (6) Sender/human reviews
  diff + REPORT, appends ACK; merge/push to main only after explicit
  human approval. (7) Next task increments id and pins a new base SHA,
  so staleness is detectable at a glance.
- Cheaper variant: skip PR for bridge-only edits — append TASK/REPORT
  directly to main in strict alternation; keep PRs for code changes. The
  GitHub Contents API (PUT with message + base64 content, sha required on
  update) is a fallback for an agent without a local clone; plain git is
  simpler and gives diffs/conflict errors locally.
- What breaks it (concurrency): both sessions editing bridge.md or main
  concurrently -> non-fast-forward push rejection plus textual merge
  conflicts in the same append region. Mitigations: turn token, one
  writer at a time, separate per-task branches, unique task ids, append
  at EOF, fetch + rebase before every push, retry-on-reject loop. Never
  force-push.
- What breaks it (liveness): GitHub stores state but does not wake an
  agent. Sessions act only when opened/prompted — expect human nudges or
  add a scheduled fetch-and-check poll later; do not claim async
  autonomy. Also breaks on: stale base SHA; dirty/monorepo
  cross-contamination (scope commits by name); committing generated
  `*.db` (gitignored) or secrets/prompts/bodies (forbidden — the file is
  public-repo-visible); token without contents/pull-request write scope;
  branch protection requiring reviews; huge/binary payloads; history
  rewrites destroying the audit trail; TASKs without id/base/turn
  fields.
- Local mapping: no bridge exists yet. api.py is read-only GET — usable
  only as verification evidence in a REPORT (e.g. /stats counts), never
  the comms channel. iris.py is a same-machine Tk launcher — irrelevant
  to cross-session comms except both agents can cite dashboard/report
  numbers. proxy.py preserves X-Trace-Id and never logs bodies/keys, so
  REPORTs may cite trace_ids/test outcomes but must not paste
  prompts/bodies. Repo facts at research time: origin
  Hogathos/python-builds, main at 747414b, suite 60/60 green.
- Upgrade path (only when single-file contention actually hurts): split
  to `docs/bridge/<task-id>.md`, one PR per task for reviewable diff +
  CI gate, GitHub Issue as the TASK envelope with bridge.md as index. Do
  not start there — more moving parts than two sessions need.

Load-bearing: turn-taking + task-id + base/result full SHAs are the
reliability mechanism. GitHub is storage/transport, not notification —
an idle session never self-wakes, so the human nudge is a required step,
not a workaround. Non-fast-forward rejection and stale-sha Contents-API
failure are the same optimistic-concurrency guard — fetch/rebase/retry,
never force-push.

Skippable: per-task files, PR-per-task, issue envelopes, polling/CI
nudges — add only when contention or scale demands it.

Proprietary: none touched — pattern uses only public git/GitHub
mechanics. Do not paste secrets, keys, prompts, or bodies into the
public-repo bridge file.

Sources:

- <https://docs.github.com/en/rest/repos/contents?apiVersion=2022-11-28>
- <https://git-scm.com/docs/git-push>
- <https://docs.github.com/en/rest/pulls>
- <https://docs.github.com/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/about-pull-requests>
- `AGENTS.md`, `agent-observability-proxy/api.py`,
  `agent-observability-proxy/proxy.py`,
  `agent-observability-proxy/iris.py`,
  `agent-observability-proxy/README.md` (local repo)

Unresolved: the other session's runtime is not defined in the repo
(local clone + git/gh credentials with write scope, or web/API only? —
  decides git-push vs Contents-API variant); whether main has branch
  protection/required reviews was not checked (if protected, per-task
  PRs become mandatory); no polling/CI trigger verified (adding one is a
  human decision under the no-recurring-jobs rule).

---

## 8. Agentic Monitoring Station inside the bridge app/IDE

Headline: Agentic Monitoring Station = live cockpit in Bridge (health,
live runs, swarm map, cost, blocked/allowed, verify, plain-word alerts);
Iris stays the history dashboard — the station reuses its API and adds
only the live/control/alert layer.

Findings:

- What it is (plain words): the live watch window kept open while agents
  work — not a report read afterwards. It answers 5 questions in words:
  (1) Are my agents alive and working right now? (2) What is each run
  doing and where is it stuck? (3) What did it cost / what is it about to
  cost? (4) What was allowed through and what was stopped, and why?
  (5) Did the finished work actually pass its checks? Bad answers come
  as sentences with one next action. A cockpit, not an archive.
- Live runs: one stream row per trace_id, newest/active first, with live
  state (running / retrying attempt N / waiting on tool / succeeded /
  failed), elapsed time, last destination + endpoint. Local source: group
  attempts by trace_id (the /traces endpoint already does latest-per-
  trace + attempt_count). Vendors agree the single run/trace is the
  clickable unit.
- Agent health: one tile per agent/destination — alive (process up + new
  attempts in last N s), slow (avg/p95 latency rising), erroring,
  looping (retries climbing — the visualizer's WASTED verdict), silent
  (expected but no attempts). Health words first ("healthy / slow /
  failing / stuck / stopped"), numbers underneath.
- Swarm map: node map agent -> destination/tool -> result, edges coloured
  by outcome (green allowed/success, red blocked/failed, amber
  rate-limited/retry), edge labels count + latency, node size = calls or
  cost. Local seed: the visualizer's per-trace Mermaid flowchart with
  SUCCESS/FAILED boxes and retry arrows; the station version is
  cross-trace and live on dest_host nodes. Limit: no agent identity in
  the schema, so v1 maps caller-trace -> destination, not named agents.
- Cost: total so far, per run, per success, wasted cost, and "unknown"
  stated openly — never invented. Local rules already correct
  (blocked/rate_limited = $0, recorded cost wins, loopback $0, external
  unknown). Vendors all do per-agent/per-model/per-conversation
  attribution — the station copies attribution and keeps the local
  honesty rule.
- Blocked/allowed: policy counter strip that must reconcile (allowed +
  blocked + rate_limited + other = total); each blocked/rate-limited row
  shows its reason in words; 403/429 counts and whether the rate limit
  has recovered. General vendors show errors; none show allowlist policy
  verdicts — this panel belongs first-screen here because the proxy is
  the policy enforcement point.
- Verify results: per finished run, a pass/fail badge separate from "it
  ran". Vendors use managed + custom LLM-as-judge evals and safety scans
  overlaid on traces, plus scores on datasets. The local station must
  not invent a quality score: show transport verdicts now
  (succeeded/failed/retried) and reserve a "checks" slot that stays "not
  checked" until a real evaluator writes score rows.
- Alerts in plain words: threshold rules as sentences ("tell me if a run
  retries more than 3 times", "if blocked calls pass 10 in 5 minutes",
  "if average wait passes 5 seconds", "if cost passes $X today", "if an
  agent goes silent for 10 minutes"). Warning before alert (two-threshold
  pattern); each alert names the run/agent, what crossed, and deep-links
  to that trace. Delivery v1: in-station banner + Iris status line;
  Slack/PagerDuty/webhook/monitors are later exports, not v1.
- Show first (station home, top to bottom): (1) health sentence line +
  proxy/API up-down; (2) policy strip (allowed / blocked / rate-limited
  reconciling to total, last blocked reason); (3) live runs list
  (active + just-finished with state, attempt, elapsed, destination);
  (4) cost line (spent today, wasted, unknown-priced runs named);
  (5) attention queue (only stuck/failing/unchecked runs, each with one
  action). Vendors lead with invocations + cost + p95 tiles — the station
  leads with health + policy because its user operates agents live.
- Fit, no duplication: the station = live + control at the point of
  work (glance health, live runs, policy verdicts, alerts, and actions
  Iris cannot do — the API is read-only GET, start/stop lives in Iris).
  The Iris dashboard = the record (full run history, per-run attempt
  detail, cost rollups). The station embeds Iris by link/iframe ("Open
  full dashboard") and reuses the same read API (/stats, /traces,
  /traces/{id}) — one SQLite source, no second store, no copied tables.
  It adds only what Iris lacks: active-vs-finished split, attention
  queue, alert rules, swarm map. If a panel already exists in Iris, the
  station shows its one-line summary + link, not a second copy.

Load-bearing: station definition verified against 4 fetched primary
sources (Grafana agent dashboard, Datadog Agent Observability, Langfuse
traces + scores + threshold alerts, OpenTelemetry GenAI conventions);
all converge on run/trace as the unit, aggregates above it, quality
scores on it, alerts as thresholds on latency/cost/error/score. Local
fit grounded in inspected code: the dashboard already covers history/
stats/cost, Iris owns start/stop, the visualizer owns static
verdicts + Mermaid, the proxy owns policy outcomes that reconcile — so
the station is the live/control layer only, fed by existing endpoints.

Skippable v1: second database; prompt/body capture (breaks the
metadata-only rule); invented cost/tokens for CONNECT tunnels; quality
score until an evaluator exists; alert delivery channels beyond the
station banner + Iris status.

Proprietary / cannot copy: vendor dashboard UI and copy; alert-channel
integrations are later exports. Name any future exported fields
`gen_ai.*` for Grafana/Datadog/Langfuse portability (OTel convention).

Sources:

- <https://grafana.com/docs/monitor-applications/ai-observability/genai/agent-observability/>
- <https://grafana.com/blog/ai-observability-ai-agents/>
- <https://docs.datadoghq.com/llm_observability/>
- <https://docs.datadoghq.com/llm_observability/investigate.md>
- <https://langfuse.com/docs/observability/overview>
- <https://langfuse.com/docs/observability/features/alerts>
- <https://opentelemetry.io/blog/2026/genai-observability/>
- Local: README.md, iris.py, api.py, db.py, proxy.py, visualizer.py,
  docs/architecture.md in agent-observability-proxy

Unresolved: no Bridge panel exists in this workspace (search "Bridge" = 0
matches) — placement assumes the external/host IDE app; true swarm map
by named agent is impossible from current data (no agent_id column —
map v1 is trace -> destination, and adding identity needs human
approval); agent health beyond process-up is inferred, not measured (no
heartbeat/last-seen per agent, /stats has avg latency only); no
verify/checks data source exists yet (TRACE_COLUMNS excludes
tokens/strategy/retry text); alert delivery channels not present
locally.

---

## Cross-topic tensions

- Enforcement vs read-only contract: topics 2, 3, and 8 all want policy
  action (per-tool allow/block, kill layers, alerts with actions), but
  api.py is read-only GET by design and AGENTS.md requires explicit
  human approval for control surfaces. Any control endpoint is a new
  contract, not an extension.
- Metadata-only vs visibility: topics 1, 3, 4, and 8 all stop at the
  same wall — CONNECT tunnels and MCP-inside-TLS are opaque by contract.
  Tool governance, swarm detection, and cost attribution for tunneled
  traffic need a terminating leg or a cooperating agent-side emitter;
  the proxy must never be taught to decrypt.
- Local-first vs cloud patterns: every vendor topic assumes cloud,
  SDKs, and per-seat metering. The local wedge (loopback, SQLite,
  flat price, plain words) is the differentiator but also the ceiling —
  fleet views, cross-machine swarms, and retention/compliance hosting
  stay out of v1 scope deliberately.
- Single file vs scale: topic 7's one-bridge-file pattern and topic 8's
  one-SQLite-source rule both optimise for two sessions / one machine.
  Both name their own upgrade path (per-task files + PRs; second store
  only if contention proves it) — do not build the scaled version
  first.

## Global unresolved

- OWASP primary PDFs and some vendor pricing pages were corroborated
  via secondaries, not fetched directly — re-check figures at build
  time; never bake a price into code without a dated official source.
- "Shield"/"Swarm map" are working names, not industry terms.
- Real-world hostile agentic-swarm evidence is still emerging, not a
  mature forensic record — detection claims must stay probabilistic and
  reviewable.
- CyberHog's runtime (local clone + credentials vs web/API only) and
  main-branch protection status were not verified — they decide the
  exact Bridge variant.



Proprietary / cannot copy: vendor agent-framework governance code,
LangChain middleware code (reimplement the pattern, not the code), MCP
sample servers verbatim without licence check.

Sources:

- <https://modelcontextprotocol.io/specification/2025-06-18/server/tools>
- <https://genai.owasp.org/llmrisk/llm062025-excessive-agency/>
- <https://docs.langchain.com/oss/python/langchain/middleware/built-in>
- <https://developers.openai.com/api/docs/guides/function-calling>
- <https://www.aicassindra.com/blogs/agents/tool_calling_reliability_timeouts_idempotency_compensation.html>
- <https://github.com/strands-agents/harness-sdk/issues/2973>
- <https://devblogs.microsoft.com/agent-framework/governance-at-the-speed-of-agents-microsoft-agent-framework-and-agent-governance-toolkit-better-together/>
- <https://www.querynow.com/ai-agents/mcp/mcp-security>

Unresolved: MCP tool annotations (readOnlyHint/destructiveHint)
unconfirmed (spec fetch truncated); OpenAI strict-mode/parallel_tool_calls
defaults from snippets, verify on the docs page before implementing
executor rules; no live MCP-through-proxy runtime test performed.

