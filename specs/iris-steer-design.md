# Iris Steer — design draft (2026-11-13)

Steer first for safety. Verify in parallel, then Verify build, then SDK. This design is Steer only, no Verify, no SDK in this build.

## What Steer is, in plain words

Steer is: can you stop it, pause it, or point it somewhere else, while it is running?

- Pause one Run — stop this one job, leave the others alone.
- Redirect one Run — send this one job to a different, safe destination, or to a dead end, instead of where it was going.
- Red button — block traffic entirely from a specific network. One button, everything from that network stops, now.

Steer lives OUTSIDE the agent loop, at the proxy / gateway. The agent does not decide whether to be steered. Iris does.

## What Steer is NOT

- Not a chart. Not "here is a graph of what happened". Steer is an action.
- Not a kill-switch only. Kill-switch already exists: proxy down = agent stops, fail-closed. Steer is finer: pause one Run, not the whole proxy.
- Not LLM-as-judge. Steer does not decide if a Run is good or bad on meaning. It acts on what a human decides, or on a clear rule: allowlist, rate-limit, spend cap, blocklist.
- Not automatic blocking by a probabilistic detector. A score is not a verdict. If Iris cannot prove a Run is bad, it says unknown, and asks a human, or lets it through with a flag — it does not silently block on a guess.

## The three actions, in detail

### 1. Pause one Run
- Human pauses Run X from the dashboard, in plain words: "Pause this Run".
- Proxy stops forwarding traffic for that Run only. Other Runs continue.
- State in SQLite: paused, with time, reason (human, or rule name), and what was in flight.
- Resume: human resumes, same Run, same state. If the destination timed out while paused, outcome = unknown, not failure. Verify before retry.
- If Iris restarts while a Run is paused, that Run stays paused. Never auto-resume on restart.
- Both options, made clear: stay paused until you resume it, OR auto-resume after a time you choose. Both shown in plain words on the pause screen, per Run, so the user is not confused which one they picked.

### 2. Redirect one Run
- Human chooses: redirect Run X to a safe destination, or to a block page / dead end.
- Use cases: agent is heading to a wrong / risky destination, send it to a safe mirror, or to nowhere, instead of letting it hit the real thing.
- Redirect is explicit, logged, plain-words: "Run X was going to example.com, redirected to safe.example.com by Charles at 2:14 PM".
- Never redirect silently. Never redirect to a destination that looks like the real one to trick the agent — that is deception, not steering.
- Safe destination list: BOTH, as long as it is coherent. User writes the list, Iris can suggest additions, Iris never invents a safe destination on its own. User's list wins, list stays human-readable.
- Automatic redirect, for user safety: if feelers / detectors detect something risky, Iris redirects automatically, to a safe destination / dead end, without waiting for a human click. This is the one auto-control allowed, because it is fail-closed and safety-first. Rules: only on a clear rule match — allowlist / blocklist, exploit DB match, taint / injection match — never on a probabilistic score alone. If it is a guess, Iris says Unknown and asks a human, it does not auto-redirect.
- Exploit DB: build / use a DB of exploits that matter for the kind of work Iris is doing — known bad destinations, known injection / taint patterns, known exfil destinations, known prompt-injection / tool-abuse patterns. Versioned, source + date per entry, never guessed. Look for a collated DB first, or build our own from verified sources. This DB is what the feelers check against. If a Run matches, auto-redirect to safe / dead end, log it, alert the human in plain words, human can Undo.
- Feelers: detectors that watch metadata only — destination, size, timing, rate, pattern — and check against the exploit DB, allowlist / blocklist, spend cap, taint list. No bodies, no keys, no MITM. If a feeler trips, it is a flag, not a verdict, unless the rule is clear-cut. Clear-cut = auto-redirect. Unclear = Unknown, ask human.
- Automatic cross-reference + proactive engage, added 2026-11-13: Iris automatically cross-references every Run against the exploit DB, allowlist / blocklist, taint list, spend cap, and past Runs from the same agent / network / destination — in real time, as traffic flows. If it matches a known threat, Iris proactively engages: auto-redirect to safe / dead end, or pause / block that Run / network, log it hash-chained, alert the human in plain words, human can Undo. Only on a clear rule match, never on a probabilistic score alone. If it is a guess, Iris says Unknown and asks a human, it does not proactively engage. Cross-reference is metadata-only, no bodies, no keys, no MITM.
- If Iris finds something, it acts on it, in a positive way. Think of it like an E3-E4 Marine engaging the enemy, Charles 2026-11-13: not just flagging it and waiting, not just logging it for later — engaging it. Positive action, in order: stop the Run, block the network, redirect to safe, all-stop if it is spreading, log it, tell the human what it did and why, in plain words. Iris does not sit and watch a threat hit the user. It engages, then reports. Human can Undo, human is still in the loop for the big call, but Iris does not wait for permission to stop a clear threat.
- Standing orders for autonomous actions, added 2026-11-13: you can tell Iris what to do in the case of its autonomous actions, not unlike giving orders in war. Standing orders, in plain words, human-written, per threat type: "If a Run matches the exploit DB, redirect it to safe, then block that network." "If an agent lies twice, pause it and alert me." "If spend hits 100%, block it, do not let it through." Iris follows your orders, not a model's opinion. Orders are a readable file, versioned, you can change them, you can Undo what Iris did under an order. No order = no autonomous action, Iris asks you. Unclear threat = Unknown, ask human, do not engage on a guess.
- Iris acts on information in its environment, and seeks to verify it for you, so you, the general, can act accordingly, Charles 2026-11-13. Verifiable information is half the battle. Iris is the scout / Marine in the field, you are the general: Iris watches, checks, verifies, engages on clear orders, then reports back with verified information — what happened, what it checked, what it could not check, what it did, why. You decide the strategy, based on verified information, not on a guess, not on a score, not on a lie.
- Safeguards against malicious trickery, added 2026-11-13: Iris will have safeguards against malicious trickery — prompt injection, taint, instruction smuggling in tool output / web pages / files, lying emitter, lying agent, fake "allow me" messages, replay / spoofed reports, exploit DB poisoning. How: never trust tool output / web content as an instruction, only as data to check; taint tracking — mark data from untrusted sources, do not act on tainted instructions; signed emitter reports, signature check; independent read-back, not agent's word; standing orders only from the human, in a readable file, never from a Run; exploit DB versioned, source + date per entry, never auto-update from an untrusted source; Unknown on unclear, ask human, do not engage on a guess. Note, honestly, Charles 2026-11-13: as much mitigation as logically able to promise, within the realm of physics and shippability. No tool can promise "all" trickery, forever — new tricks appear. Iris promises safeguards against known trickery, and Unknown + human in the loop for new trickery, not a fake guarantee.

### 3. Red button — block this network
- TWO levels, both shown clearly: (1) Emergency all-stop — stops ALL traffic, now, for all Runs and all networks. (2) Individual control — "Block traffic entirely from this network", per network / destination.
- Effect: all traffic to/from that network stops immediately, for all Runs, until a human unblocks it. All-stop does the same, for everything.
- Individual stops are user-labelable: the user can name a stop whatever they want, in their own words, for simplicity and to keep track — e.g. "bad API", "test network", "do not touch". The label is shown in the dashboard, in plain words, next to the network / destination it stops.
- Networks / agents are labelable too: the user can label and keep track of their networks and agents, in their own words — e.g. "work agent", "test agent", "home network", "Muse Code". Labels show in the dashboard, in plain words, next to the Runs they belong to, so the user can tell at a glance who did what, where. This ties to Identity / Passport: a label is the human name for an agent / network, the passport is the signed identity underneath it.
- Fail-closed: if Iris crashes, or the policy layer is unavailable, traffic stops. Never fail-open.
- Unblock is human-only, logged, with reason. No auto-unblock on timer, unless Charles explicitly sets one, with a plain-words expiry.

## Control endpoint — new contract, needs explicit approval

The API today is read-only GET by design: /health, /traces, /traces/{id}, /stats. Steer needs a control endpoint, and that is a NEW contract, not an extension.

- Control actions are POST, never GET. GET must never change state.
- Control endpoint is loopback only, 127.0.0.1, same as the API today. No remote control.
- Auth: local-only, no token in the log, no key in the dashboard. If a control endpoint is ever exposed beyond loopback, that is a separate decision, with Charles's explicit approval.
- Every control action is logged in SQLite, hash-chained, plain-words: who (human, or rule), what, when, which Run / network, why.
- Fail-closed: if the control endpoint is down, or the policy is unavailable, the proxy stops forwarding. Never continue on a stale policy.
- No control action without a human-readable reason shown in the dashboard, before and after.

Charles must approve this control contract in words before it is built. Do NOT add a control endpoint in a Verify task, or as a side effect of another build.

## Rules, in plain words

- Allowlist: destination is on the list, let it through. Not on the list, block with 403, no tunnel on CONNECT.
- Rate-limit: too fast, slow it down with 429, with recovery. Tell the human why.
- Spend cap: USER-DEPENDENT, PER PROJECT. Warn at ~80%, block at 100% are defaults only. User sets their own warn / block numbers, per project, per Run / per day / per month, per destination / agent when we have agent_id. That is coherent because it is per project — each project has its own budget, its own numbers, its own meaning. Provider-reported usage only, never invented. $0.00 if unreported.
- Autonomy budget: write / execute / commit limits, per Run. When the budget is hit, pause, do not kill silently. Tell the human.
- All rules are files a human can read, not hidden ML. Policy as a file, plain words.

## Dashboard — what the human sees

- One Run, one row: "Run f2784ae6 — Tried GET example.com/ — blocked by the allowlist."
- Steer buttons on that row, in plain words: Pause, Redirect, Block this network.
- After an action: "Paused by you at 2:14 PM. Reason: you paused it." / "Blocked example.com at 2:14 PM. All traffic to example.com is stopped."
- No trace_id without "Run". No stat without its meaning. No jargon.
- Every tool is labeled clearly in the GUI for what it is going to be used for, in plain words. No SWE baggage. Idea from Matt's Go Do Stuff agent, not a copy of his design: simple, one job per button, what it does is written on it, in plain language a normal person can read. No spans, no OTel, no trace IDs, no dev terms in the consumer app.
- Dev-only helpers stay out of the consumer app. Test button / diagnostics / raw logs / db path = dev-only, separate file/panel.

## What happens when Steer is wrong

- Pause a good Run: human resumes, outcome = unknown if it timed out, Verify before retry. No data loss in the log.
- Block a good network: human unblocks, log shows who blocked, when, why. No silent auto-unblock.
- Redirect to the wrong place: log shows the redirect, human can undo it. Never claim the redirected Run did the original thing.

## Security — best practices, so Iris is not malware, and cannot be used as malware

Charles's worry, 2026-11-13: "I don't want people accusing me of making malware when they download from my public repo." Update security measures continuously, until needed, not once at the end.

- Loopback only, no remote, ever. Control endpoint listens on 127.0.0.1 only. No 0.0.0.0, no LAN, no internet.
- No auto-control, human in the loop. Steer actions are human-initiated, or rule-initiated with a human-written rule. Iris never pauses / blocks / redirects on its own because a model told it to. No LLM-as-judge deciding to kill a Run.
- Least privilege, fail-closed. POST only, GET never changes state. If the endpoint is down, or the policy file is missing / corrupt, traffic stops. Never continue on a stale policy. Iris runs as your user, not as admin, not as a service with system rights.
- Audit everything, hash-chained, plain words. Every control action logged: who, what, when, which Run / network, why. If Iris ever does something you didn't ask for, the log shows it.
- No remote code, no auto-update of policy. Policy is a file you can read, on your machine. Iris never downloads a policy from the internet, never auto-updates its allowlist / blocklist from a cloud feed, unless you explicitly tell it to, from a source you named, with a date + source per entry.
- No bodies, no keys, no headers in the log. A compromised Iris cannot leak what it never logged.
- Separate the planes. Control plane (Iris UI, your clicks) separate from data plane (proxy forwarding). GUI closing doesn't kill traffic, proxy dying doesn't leave control open. Never policy inside the CONNECT relay.
- Open source, transparent, signed. Repo is public, code is readable, no obfuscation, no hidden network calls. README states plainly what Iris does and does not do: local only, metadata only, no MITM, no bodies, no keys, fail-closed. Consumer .exe is code-signed when distributed. No auto-update that could swap in a bad version. SECURITY.md in the repo, with how to report a problem, and what Iris will never do.
- What this does NOT solve: if someone already has access to your Windows machine, they can click the same buttons you can. That is a Windows problem, not an Iris problem — Iris doesn't add a new remote hole. If you install a malicious plugin / MCP server, Iris can't stop that server from doing bad things inside its own process. It can only stop its traffic at the proxy.
- Enterprise is a different problem: scale, RBAC / SSO, multi-machine logs, compliance audit acceptance. Consumer wedge first, enterprise proof underneath, enterprise product after.

## Known unknowns — what Iris knows it does not know

Keep Unknown in the GUI, as a state, not a button. Iris tells you when it does not know, instead of guessing. That is the proof, not the weakness. Other tools show $0.00 / Success / a score when they do not know. Iris says Unknown, and says why.

1. Inside a TLS tunnel — destination, size, timing only. No tool name, no message, no meaning. No MITM, by design.
2. Tool calls inside that tunnel — which tool, what it asked, what came back. Only a loopback gateway or optional SDK can tell Iris that.
3. Semantic correctness, from wire traffic alone — a 200 OK does not prove the file was the right file, or the invoice was the right amount. Meaning lives in the destination, not on the wire.
4. Per-tool cost, for tunneled traffic — Run cost if provider reports tokens, no split per tool / agent without an emitter.
5. Named-agent swarm identity — traces to destinations, no agent_id / owner / permission unless the agent tells Iris via passport / SDK.
6. Timeout = unknown — if a Run times out after it might have committed, Iris does not know if it happened. Unknown, not Failed, not Success. Verify before retry.
7. Memory / context — what an agent remembered, what was in context when it made a call, what it leaked into memory. Needs an emitter, not a proxy.

Unknown as proof: dashboard shows Unknown counts, log shows what was checked and what was not, audit pack shows the evidence. Unknown never becomes an action. Iris never blocks, pauses, or redirects on an Unknown. It asks a human, or lets it through with a flag.

## Bending the constraints — without breaking them

AI governance is hard because it is opaque. Iris clears up opacity by moving the observation point, not by decrypting:

1. Terminating leg — loopback gateway. Agent talks to a local MCP gateway on loopback, in plain JSON-RPC. Iris sees tool name, call, result, because the agent chose to talk there, in plaintext, on your machine. Gateway then talks out over TLS. No MITM, no decryption.
2. Cooperating emitter — optional SDK. Agent tells Iris what it did, metadata only. Tool name, argument shape, result read-back, agent_id, cost per tool. No bodies, no keys. Opt-in, because the agent wants to be governed.
3. Read-back, not wire-reading. Check the destination after. File exists? Row in the DB? Email has a message ID? Destination is the source of truth, wire is a hint.
4. Journal-first + postconditions. Agent writes its intent automatically, before it acts — "I am about to write invoice #123 for $50 to Acme" — with an idempotency key. Human defines "done" once, per task type, not per Run. Iris checks the postcondition after. Automation stays. If the human had to write every intent by hand, that would defeat automation. That is not the design.
5. Identity / Passport, signed, local. Id, owner, purpose, scoped expiring credential, provenance chain human → agent → tool. Attach to every metadata row. Swarm Map becomes named agents, with permission, in plain words. No cloud identity service.

## Emitter — separate collaborator, not in-agent

The emitter is a separate process, not in the agent's process. Like a collaborator / informant reporting about the agent, not for it.

- Agent cannot kill it, edit its reports, or see its key.
- Emitter signs its reports. Iris checks the signature. Wrong signature, or missing report = Unknown, not "agent said it was fine".
- Emitter does not trust the agent's word alone. It cross-checks with read-back.
- If the emitter goes silent, Iris notices. Silence is a signal, not a pass. A pattern of missing reports is a flag.

If the emitter gets co-opted, Iris still has the wire metadata, the read-back, and the signature check. A lying emitter is caught by the independent check, not by trusting it.

## Verify → Steer loop — if the agent is lying, Iris checks, and if malicious, acts

Claim → independent check → lie / malicious → action.

- Agent says "I did it" → Iris checks, independently, by read-back. File exists? Row in the DB? Email has a message ID? Not by trusting the agent, not by trusting the emitter alone.
- If the check says no, or the claim does not match what Iris saw on the wire, or the emitter's report does not match the read-back — that is a lie, or a mistake. Iris says so, in plain words: "Agent said it wrote invoice #123, read-back found no such row."
- If it is malicious — same lie, repeated, or a pattern, or a tainted instruction, or a blocked destination tried again — Iris takes appropriate action, in order: Pause that Run, Block that network / destination, All-stop if it is spreading, Log it hash-chained, so you have proof.
- Human is still in the loop for the big call, but Iris does not wait for you to notice a lie. It checks, it flags, it pauses, then it tells you.

## Multi-agent jobs / project groups — added 2026-11-13

For multi-agent jobs, group projects together, and stop / pause / block them as a group, not just one Run at a time.

- A project group is a set of Runs / agents / networks, grouped by the user, in their own words — e.g. "website build", "tax review", "swarm test". Label + unique ID, same unified label system.
- Group actions: Pause this group, Resume this group, Block this group, Redirect this group, Stop everything in this group. One click, all Runs in the group, not one by one.
- Group cost: total cost for the group, per Run inside it, Unknowns per group.
- Group Unknowns: if one Run in the group is Unknown, the group shows it, does not hide it.
- A Run can be in one group at a time, to keep it simple. Moving a Run to another group is human-only, logged.
- All-stop overrides group stops, same as individual stops. GUI says so in plain words.
- Projects, labeled too. A project is a set of groups / Runs, labeled in the user's own words — e.g. "Iris build", "website", "tax review". Iris accommodates multiple projects at once, side by side, each with its own budget, its own spend cap, its own groups, its own cost total. You can tell projects apart at a glance by label + ID, filter by project, pause / block / stop by project, export by project. No project is hidden, no cost is mixed across projects.

## Useful features — added 2026-11-13

- Search / filter the log — find a Run by destination, agent label, date, "blocked only". Newest first is not enough.
- Undo — pause the wrong Run, block the wrong network? One Undo button, in plain words, with what it undoes. No "are you sure?" maze.
- Alerts, in plain words — "Agent tried to go to a blocked network 5 times in a minute". Small alert, not a noisy alarm.
- Export / share a Run — one click, export one Run as a plain-words file: what it did, what Iris did, cost, Unknowns. Evidence pack, per Run.
- History / replay, honestly — re-show the exact metadata timeline, step by step, what was blocked / allowed. Not "re-run it exactly" — we cannot promise that — just re-show it.
- Start / stop cleanly — Iris starts when you double-click, stops when you close it, tells you in plain words if a Run was paused when you closed it. No silent state loss.
- "What happened today" summary — one screen: X Runs, Y allowed, Z blocked, total cost, any Unknowns, any lies flagged. Plain words, no chart maze.

## Tabs at the top — Iris wears a lot of hats

Different jobs, different tabs at the top, switch between all the info, in plain words:

- Watch — "See what your agent does"
- Verify — "Check if it actually did it"
- Steer — "Pause, redirect, or stop it"
- Cost — "What it cost"
- Projects — "Your projects, groups, and labels"
- Alerts — "What Iris flagged, in plain words"
- Today — "What happened today"

One tab at a time, one job at a time. No maze, no hidden panels. Tabs are the hats — Iris wears a lot of them, you pick the one you need right now.

Charles, 2026-11-13: "It's like I'm making an agentic anti-virus network software." Yes — that is the shape. An anti-virus for agents, on the network, locally, in plain words: watch what it does, check if it lied, stop it if it is malicious, tell you what it cost. Not a traditional AV — no file scanning, no signatures on disk — but the same job, for agents: protect the user while the agent runs.

First principles matter, never forget where ya came from. Include traditional AV stuff where it matters, adapted to agents:

- Signatures — traditional AV has signature DBs for known malware. Iris has an exploit DB for known bad destinations / patterns / CVE-linked agent behavior. Same first principle: known bad thing, known signature, block it.
- Heuristics / feelers — traditional AV watches for suspicious behavior, not just known signatures. Iris's feelers do the same, on metadata: rate, size, timing, destination, pattern. Suspicious = flag, not verdict, unless clear-cut.
- Quarantine — traditional AV quarantines a file, does not delete it silently. Iris pauses / blocks a Run / network, does not delete the log, human can Undo / Unblock. Same principle: stop it, keep the evidence, let the human decide.
- Real-time protection — traditional AV watches as files are opened. Iris watches as traffic flows, in real time, fail-closed. Same principle: protect while it runs, not after.
- Updates — traditional AV updates signatures. Iris updates the exploit DB, versioned, source + date per entry, from verified sources, never guessed. Same principle: known bad things change, the DB changes with them.
- Do not include what does not matter: file scanning on disk, registry scanning, browser extensions, email scanning. That is not Iris's job. Iris is network + agent behavior, not a disk AV.

Charles, 2026-11-13: Iris is "a swarmchaser helper agentic anti-virus proxy monitor autonomous shield". Enmeshed, not stacked: swarmchaser helper + agentic anti-virus + proxy + monitor + autonomous shield, all in one local app, all metadata-only, all plain words. Charles, 2026-11-13: "Sounds schizophrenic." Agreed — do NOT pitch it that way. Front line, one sentence only: "Iris is a local app that watches an AI agent, and stops it when it does something wrong." The five-hat line stays in the design only, not in the pitch. Bring out one hat at a time, depending on who you are talking to: Rowan = helper / evidence pack, consumer = anti-virus for agents, evaluator = local agent governance.

Rachel @chaotictransfem, 2026-11-13, X: personal agent system, full proactivity, memory with dreaming, SwiftUI interpreter for live dynamic native UI from your agent, safe auto-review / dangerous action prevention. Not open-sourced yet, asking should I open source. Different lane from Iris — personal agent, not governance proxy. Keep SwiftUI dynamic UI idea in mind for Iris app mode / IDE, idea only, no copy. Possible pitch later: work together, if she would like verification that her agent works — Iris Verify for her agent. Her agent does things, Iris watches it, checks if it actually did it, in plain words, with evidence. Do not pitch without Charles's word. Wait until Verify is ready to show, after Lightcone closes Nov 15.

Iris splash screen — CHOSEN 2026-11-13, Charles: YES. Halo-corrected version, file `media-generation-iris-splash-halo-corrected-0-b054b9d2-8c73-4bf7-bf30-441c6f38438b.webp`. Halo 3 splash composition: one huge central faceted diamond gate, glowing rainbow arc as visor, faded side figures, dark background, small logo bottom right, no large text. Ancient Greek pottery motifs, simple black-figure, terracotta and black. Earlier versions rejected: first literal goddess version too literal, Quake/Halo version, Greek pottery version — corrected Halo version is the chosen one.

## Agentic software to learn from — where it matters

Not just AV, agentic software too. Same rule: take the function, improve upon it, make your own design, because you can do better than they can.

- LangSmith / Langfuse — trace timeline, per-Run cost, search / filter, evals. Learn: timeline + cost + search. Discard: cloud-only, SDK-required, observe-only, no enforcement, no plain words.
- AgentOps — session replay, time-travel, cost per session. Learn: replay honestly, session view. Discard: cloud, SDK, no Steer.
- OpenAI Agents SDK / Claude Code — tool calls, handoffs, guardrails. Learn: tool-call shape, guardrail as a rule, handoff as a group. Discard: tied to one model / vendor, no local proxy, no plain language.
- AutoGen / CrewAI — multi-agent, groups, roles, handoffs. Learn: group = project group, role = label, handoff = group action. Discard: framework-only, no governance, no cost, no kill-switch.
- Muse / Cursor / Windsurf — agent in the editor, runs tools, writes files. Learn: agent as a worker you watch, not a black box. Discard: no network view, no cost per Run, no Steer.
- Heimdall MCP / Argus / Eidolon — per-tool policy, priced cost, kill / revoke. Learn: policy, cost, kill. Discard: dev-only, MCP-only, enterprise-only.
- MCP servers in general — tool as a JSON-RPC call, plaintext on loopback. Learn: terminating leg, loopback gateway. Discard: no governance on top, trust the server.
- LangChain / LlamaIndex — tool use, memory, RAG. Learn: memory audit idea, tool as a call with a contract. Discard: framework bloat, no local enforcement.

AV + agentic, together: AV gives Iris the protection shape — signatures, heuristics, quarantine, real-time, updates. Agentic gives Iris the work shape — traces, tool calls, groups, handoffs, cost, memory. Iris is both, enmeshed: an agentic anti-virus, not a disk AV with an agent tab, not an observability dashboard with a block button.

## AV software to learn from — where it matters

- Windows Defender / Microsoft Defender — real-time protection, quarantine, definitions update, plain language for normal users. Learn: how it says "threat found, quarantined" without jargon.
- Malwarebytes — simple, one job per screen, "scan, quarantine, allow". Learn: simplicity.
- Little Snitch (Mac) — network firewall, "this app tried to go here, allow / deny once / forever". Learn: per-destination allow / deny, in plain words, at the moment it happens.
- Pi-hole — blocklist, allowlist, "blocked X queries today". Learn: blocklist as a readable list, stats in plain words.
- ClamAV — open source, signature DB, no cloud. Learn: open DB, versioned, offline works.
- CrowdStrike / SentinelOne — enterprise EDR, "kill process, isolate host". Learn: isolate = pause / block, but discard: cloud-only, enterprise-only, no plain language.

## AV labels — draft

- Quarantine — "Stop this job, keep the evidence"
- Threat found — "Iris found something risky"
- Safe — "Checked, nothing risky found"
- Allow this — "Let this through, I trust it"
- Trust this network — "Let traffic from this network through, I trust it"
- Exploit DB — "List of known risky things Iris checks against"
- Feeler tripped — "Iris noticed something odd"

## Design constraints — adapt what matters, discard what does not

Charles's motto, 2026-11-13: "Take the function, improve upon it, make your own design, because you can do better than they can." Keep this in mind with all questions like these. It matters.

Look at what other products of this kind do, adapt what matters, discard what does not. Not an exact copy. Take the function, improve upon it, make your own design.

Every product of this kind is derivative — that is impossible to avoid completely. Watch, Verify, Steer, Meter, cost, logs, kill-switch — those are functions, not inventions. What matters is how Iris does them: locally, metadata-only, plain words, fail-closed, human in the loop, no SDK, no cloud, no guessing.

Adapt:
- From LangSmith / Langfuse / AgentOps: trace timeline, per-Run cost, search / filter. Discard: cloud-only, SDK-required, observe-only, no enforcement.
- From Heimdall MCP: per-tool allow / deny, policy. Discard: MCP-only, dev-only, no plain language, no cost.
- From Argus: priced cost per turn. Discard: Claude / Codex only, dev-only, no block / kill.
- From Eidolon: kill / revoke, governance. Discard: MCP gateway only, enterprise-only, no cost, no plain language.
- From Wireshark / mitmproxy: see traffic, count bytes. Discard: network-only, no agent understanding, no plain words, no enforcement.
- From Matt's Go Do Stuff agent: get an idea, do not copy him design-wise. Simple, one job per button, what it does is written on it — that is the idea to take, not the design to copy. Same reasoning as Argus / Heimdall / enterprise cloud products: look at them, take the idea that matters, discard the rest, build Iris's own version.

Clean-room: replicate function, not code, not UI, not copy. Do not copy LangSmith / Langfuse trace UI, evaluator prompts, judge rubrics, pricing-page copy. Do not reuse LiteLLM / Helicone gateway code. Do not clone AgentOps time-travel or Phoenix OTel UI. Build metadata-only views from Iris's own SQLite schema. MCP is an open spec, implement freely, do not copy sample server code verbatim without a licence check. No TLS MITM, no body / secret logging.

## What they miss out on — what Iris adds for the user

Competitors miss these, Iris adds them, for the normal person, not the dev team:

- Enforcement, not just charts. They show you a trace. Iris lets you pause, block, redirect, all-stop. That is the difference between watching a fire and having a fire extinguisher.
- Plain words, not SWE terms. They show spans, OTel, trace IDs. Iris shows "Run f2784ae6 — Tried GET example.com/ — blocked by the allowlist." A normal person can read it, act on it, explain it to someone else.
- Local, no cloud, no SDK. They need you to install an SDK, send your data to their cloud, pay per seat / per trace. Iris is double-click, point the agent at the proxy, data stays on your machine, no per-seat meter.
- Unknown, honestly. They show $0.00 when they do not know the price, Success when they do not know the outcome, a score when they do not know the meaning. Iris says Unknown, and says why, and never acts on an Unknown.
- Verify, semantically. They do evals / LLM-as-judge in the cloud, tied to SDK. Iris checks if the thing actually happened, by read-back, postconditions, contracts, journal-first — meaning, not just a 200 OK.
- Per-project spend caps, user-set. They do post-call accounting, per-key budgets in the cloud. Iris does pre-call hard caps, warn at a number you set, block at a number you set, per project.
- Labels, in your own words. They give you IDs. Iris lets you name a network, a stop, an agent whatever you want, so you can keep track.
- Undo, search, alerts, export, daily summary. They have dashboards. Iris has a daily summary in plain words, an Undo button, a search box, and a one-click export of one Run for Rowan, for a boss, for a dispute.
- Kill-switch that actually kills. Proxy down = agent stops, it does not go direct. Fail-closed, proven, not a promise.
- Security you can read. SECURITY.md in plain words, open code, no hidden network calls, no MITM, no bodies, no keys. If you do not trust it, do not run it.

## Alok Pandey cold read — DIGESTED 2026-11-13

Discussion #8587, mitmproxy, Nov 13, 2026. Hils: "Zero capacity to review AI repos, sorry." Closed. Alok Pandey gave the substantive read — not a mitmproxy maintainer, role unverified.

What it means, in plain words:
- Blind spot is real, twice over. B→C downstream hops: proxy only sees A→B, B calling C is invisible. Inside CONNECT tunnels: 50 logical requests can look like 1 row, because Iris sees only CONNECT host:port, total bytes, tunnel lifetime, not method / path / per-request counts.
- Fail-closed is only as good as the agent's cooperation. Many binaries / libraries ignore HTTPS_PROXY, or use QUIC / UDP / direct DNS. Kill-switch catches well-behaved HTTP only, unless egress is enforced at OS / network-namespace level. That is a limit to name honestly, not a bug to hide.
- 30s relay timeout is too blunt for streaming. SSE / WebSocket LLM turns can idle >30s between chunks. A blanket timeout kills valid long-thinking turns. Timeout must be generous or configurable per-host, and a timeout outcome stays Unknown, not Failed.
- Allowlist friction is real. OAuth / redirects / telemetry break strict allowlists unless the exact rejected host:port surfaces immediately, so the human can allow it or fix the list.
- Trace is missing direction, outcome, and timing. Split bytes_tx vs bytes_rx — outbound spike is an exfil signal. Add close_reason / outcome — client_eof, upstream_reset, blocked_allowlist, rate_limited, relay_timeout — otherwise healthy vs failed retry is indistinguishable. Add connect_ms / duration_ms — separate DNS / TLS stalls from slow responses. Label HTTP vs CONNECT rows honestly — do not show method / endpoint / attempt_count as per-request when the row is an opaque tunnel.

Folded into design as constraints:
- Trace fields to add: bytes_tx, bytes_rx, close_reason, connect_ms, duration_ms, row kind HTTP vs CONNECT, with plain-words meanings in GUI.
- Pause / timeout: in-flight pause cuts tunnel, outcome Unknown; relay timeout configurable per-host, generous default, never a silent kill of a valid stream.
- Allowlist UX: rejected host:port shown immediately, in plain words, with Allow / Block / add-to-list on that row.
- Honest replay / Unknown: CONNECT rows shown as one tunnel, not as 50 requests; downstream B→C is a known unknown, shown as Unknown, not guessed.
- Lightcone line "No second reader yet" is now stale — Alok gave a substantive technical read, not from Hils. Whether to cite Alok in Lightcone is Charles's call.

## SDK — own, thin, optimized

Own SDK, not someone else's. Thin, metadata-only at the floor, structured semantic events at the ceiling. Built on open MCP JSON-RPC on loopback, so any MCP agent can use it without a special Iris library. No LangSmith / Langfuse / AgentOps SDK — those are cloud, their dashboard, their pricing. OTel is generic and heavy. MCP is a protocol, not a vendor — use that as the wire format. Adapters to import LangSmith / Langfuse / AgentOps traces later, if needed — read their traces in, do not live inside their SDK.

SDK shape, optimized:
- Structured semantic event, fixed shape Iris can check, not raw wire metadata, not full payload.
- Intent, before it acts: what it will do, to achieve what, done means what file / row / ticket changes.
- Tool call: tool name, argument shape only — not secret values, not full bodies.
- Outcome: result shape, hash of the proof, pointer to where Iris can check it independently.
- Proof pointer: hash + location, not the body itself. Content stays where it was, Iris reads it back locally if it needs to, never logs it.
- Signed, separate process, not in-agent. Iris cross-checks with read-back. Silence is a signal. Lying emitter caught by independent check.
- Optimize for: minimal fields, minimal overhead, batching, local only, no network call per event, no serialization bloat, no extra dependency. One event per tool call, not per byte. No bodies, no keys, no prompts in the log — ever. Full payload is NOT better — that is MITM with a nicer name.

Ladder: metadata-only (proxy today) → structured semantic events + proof hashes (SDK, Verify) → read-back to confirm (Verify) → Steer if it lies.

## Code style — non-AI slop, context window target

Repo and all code should look human-written, not AI slop. Short, direct, no fluff. No generic AI phrasing, no emoji, no "comprehensive / robust / seamless", no invented abstraction layers. Plain-words user-facing strings stay — that is Iris's voice. KEEP verbose comments and docstrings — a human found / wrote them, they are part of the code, not slop. Do not strip them to look terse.

Prompts to Muse Code stay short, one task, one file, context window target: do not paste whole files, work from repo files as they are, read only the section being changed. Trace fields + networking fundamentals are folded into one Spark prompt: iris-networking-fundamentals-spark-prompt.md, with iris-trace-fields-spark-prompt.md as detail, not re-pasted.

## Order

1. Design — this file, pick apart with Charles.
2. Networking fundamentals + Alok trace fields — Spark prompt above, one task.
3. Control contract approval — Charles says yes in words. Hold until semantic report lands, 2026-11-13 18:10 EST, then approve Steer + Verify together.
4. Build Pause one Run, then Red button, then Redirect. One at a time, tests each.
5. Then Verify, then SDK, then app mode.

## Gaps — ANSWERED 2026-11-13 13:33 EST

- Gap 2, in-flight Run on pause: BEST PRACTICE, IMPLEMENT. Cut the tunnel mid-flow. Pause = stop forwarding immediately, close the CONNECT tunnel / HTTP request in flight, outcome = unknown, not failure. Verify before retry. Letting it finish defeats the pause — that is fail-open, and Iris is fail-closed. This is the circuit-breaker / kill-switch pattern: cut, log, verify later.
- Gap 3, safe destinations: YES. Look for a collated DB of safe destinations, or build our own, without guessing. Never invent a safe destination. Sources to check: official provider / vendor lists, loopback / local only, curated allowlist with source + date per entry. If no collated DB exists, build our own from verified sources, versioned, with attribution. Unresolved until researched.
- Gap 4, all-stop vs individual: ALL-STOP OVERRIDES INDIVIDUAL. All-stop stops everything, individual unblocks do not lift all-stop. Difference made clear to the user in the GUI, in plain words: "All-stop is on — individual stops are paused until you lift all-stop."
- Gap 5, labels: UNIFY, with modularity. One label system for network / stop / agent altogether — label + unique ID underneath, shown together in the dashboard. Modularity stays: each entity (network, stop, agent) can have its own label, in the user's words, but they all use the same label system, so the user is not learning three different systems.
- Gap 7, GUI labels: BOTH. Charles and CyberHog both clear and write GUI labels together, in plain words, no SWE baggage, like Matt's Go Do Stuff agent. Then cook the prompt.

## Open questions for Charles — ANSWERED 2026-11-13 13:23 EST

- Pause: BOTH options available, made clear so the user is not confused. A paused Run can stay paused until the user resumes it, OR auto-resume after a time if the user chooses that. Both options shown in plain words on the pause screen, user picks per Run.
- Red button: BOTH. Emergency all-stop, AND individual control per network / destination. All-stop stops everything, now. Individual buttons stop one network / destination only. Both shown clearly, no confusion about which is which.
- Redirect: BOTH, as long as it is coherent. User writes the safe destination list, Iris can suggest additions, but Iris never invents a safe destination on its own, and the list stays coherent / human-readable. User's list wins.
- Spend cap / autonomy budget: USER-DEPENDENT, PER PROJECT. Warn at 80%, block at 100% are defaults only. User sets their own warn / block numbers, per project, per Run / day / month, per destination / agent. Coherent because it is per project — each project has its own budget. No hard-coded numbers that fit everyone.
- Individual stops: user-labelable, whatever name the user wants, for simplicity and tracking.
- Networks / agents: user-labelable and trackable, in the user's own words. Labels show in the dashboard, tied to Identity / Passport underneath.

## Decisions — 2026-11-13 19:11 EST, Charles, from Semantic Part 1

**Who writes "done" (postcondition):**
Default = agent proposes, human approves. You + agent, human in the loop.
That means: agent drafts the "done" definition (per task type, once, not per Run), human approves it before Iris uses it to check. No agent-written postcondition ships unapproved — agent grades its own work otherwise.
Automation (user-written, or per-tool default shipped with Iris, with no per-Run human approval) only if the user explicitly desires that risk, or the risk is mitigated. Otherwise the first two options — user, or per-tool default — are NOT the default; agent-proposes + human-approves is.
In short: human in the loop by default, automation is opt-in risk, not the default.

**Claims channel — order confirmed:**
1. Loopback gateway first — agent talks plaintext JSON-RPC to local MCP gateway on 127.0.0.1, Iris sees that leg, no MITM, no SDK required to start.
2. Optional SDK / emitter second — thin, structured semantic events + proof hashes, signed, separate process, cross-checked with read-back.
3. Read-back always — claim without read-back is Reported, never Correct.

**Remote read-back credential — still open:**
Default in Part 1 is Don't (remote stays Unknown), opt-in read-only credential in OS store, explicit "Check" only, never logged. Charles has not decided this one yet — decide with Part 2 / Steer+Verify approval together.

**Remote read-back credential — DECIDED 2026-11-13 19:14 EST, Charles:**
1 + 2. Default = Don't. Remote effects stay Unknown unless something local proves them.
Opt-in = read-only credential, later. User supplies it, lives in OS credential store, used only by explicit "Check", never logged.
Reason, Charles: "the purpose of the tool is to make things easier, not harder."
Workarounds for v1, no credential stored: human paste (ID/link, Iris checks what it can), local proof (webhook to loopback, local receipt/file Iris reads itself), public / unauthenticated reads where they exist. Agent does the read-back = no, weak, agent grading its own work.
