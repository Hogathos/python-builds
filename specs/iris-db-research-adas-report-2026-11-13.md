# Iris DB research — for Charles

From: Adas Date checked for all sources: 2026-11-13
Rules used: local only, metadata only, no MITM, no bodies, no keys, fail-closed, human in the loop. User writes the safe list. Iris can suggest, never invents. Never redirect to a lookalike to trick the agent. Clear rule match only = engage. Probabilistic score alone = Unknown, ask human. Never auto-update from an untrusted source.
Method: 5 parallel research agents + 1 skeptic re-fetch pass. Every URL below was fetched on 2026-11-13. Where a source could not be verified from the primary page, it is in Section 5, not guessed.

## 1. Safe destinations — collated DBs found, or none found

Plain answer: none found. No verified, ready-made collated DB of safe redirect targets (safe mirror / dead end / loopback) for agent traffic was found.

What does exist, and must not be confused:

* Discovery registries — not safety approval. Official MCP Registry — registry.modelcontextprotocol.io/ — checked 2026-11-13. Publisher metadata only, listing does not mean safe. Same for GitHub MCP Registry — github.com/mcp — checked 2026-11-13, and official reference servers — github.com/modelcontextprotocol/servers — checked 2026-11-13. Registry code confirms this: github.com/modelcontextprotocol/registry — checked 2026-11-13. Use to find candidates only.
* One strongly curated catalog — suggestion source only. Docker MCP Catalog — docs.docker.com/ai/mcp-catalog-and-toolkit/catalog/ and hub.docker.com/mcp — checked 2026-11-13. Signed, SBOM, versioned, supports custom catalogs. Best suggestion source found. Iris may suggest from a pinned version/digest. User still writes each entry in. No auto-add.
* Enforcement tools — mechanism, not a list. Squid dstdomain — www.squid-cache.org/Versions/v6/cfgman/acl.html — checked 2026-11-13. GitHub Agentic Workflow Firewall — github.github.com/gh-aw-firewall/ — checked 2026-11-13, usable only with SSL Bump off. Anthropic sandbox-runtime allowedDomains — github.com/anthropics/sandbox-runtime — checked 2026-11-13. Docker MCP Gateway — github.com/docker/mcp-gateway — checked 2026-11-13. All consume a user-written list. None supply one.
* Loopback / local only — the only verified candidate safe sinks. localhost / *.localhost always loopback — www.rfc-editor.org/rfc/rfc6761.txt — checked 2026-11-13. 127.0.0.0/8 and ::1 host-local only — www.rfc-editor.org/rfc/rfc1122.txt — checked 2026-11-13. Check any block is not globally reachable before use — www.iana.org/assignments/iana-ipv4-special-registry/iana-ipv4-special-registry.xhtml (last updated 2025-10-09) and www.iana.org/assignments/special-use-domain-names/special-use-domain-names.xhtml — checked 2026-11-13. Background: www.rfc-editor.org/rfc/rfc6890.txt — checked 2026-11-13. Even these go in only when the user writes them in.
* Provider endpoints are detection, not safe targets. OpenAI api.openai.com — developers.openai.com/api/reference/resources/beta/subresources/agents/methods/create — checked 2026-11-13. Anthropic api.anthropic.com — platform.claude.com/docs/en/get-started — checked 2026-11-13. Google generativelanguage.googleapis.com — aistudio.google.com/docs/openai — checked 2026-11-13. These mark the real cloud destination. Never mimic them.

Home-built Safe DB should be built from: user-written loopback/local entries above, suggestions only from the Docker catalog with pinned digest, enforced with Squid-style domain match or sandbox-runtime allowedDomains. Versioned file, source + date on every entry.

## 2. Exploit DB — collated DBs found, or none found

Plain answer: no single collated Exploit DB for Iris was found. Build one locally from these pinned parts:

* MITRE ATT&CK — best metadata rules. attack.mitre.org/ free, no cloud needed — checked 2026-11-13. Pin version — attack.mitre.org/resources/versions/ shows v20.1, 13 Oct 2026 — checked 2026-11-13. Clear-match techniques on destination/protocol/tool metadata: T1700 attack.mitre.org/techniques/T1700/, T1567 attack.mitre.org/techniques/T1567/, T1041 attack.mitre.org/techniques/T1041/, T1048 attack.mitre.org/techniques/T1048/, T1071 attack.mitre.org/techniques/T1071/, T1059 attack.mitre.org/techniques/T1059/, T1105 attack.mitre.org/techniques/T1105/ — all checked 2026-11-13.
* CISA KEV + NVD — only if product/version is known in metadata. KEV catalog www.cisa.gov/known-exploited-vulnerabilities-catalog and feed www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json (catalogVersion 2026.11.13, 1781 entries) — checked 2026-11-13. NVD API 2.0, e.g. services.nvd.nist.gov/rest/json/cves/2.0?cveId=CVE-2025-32711 and CVE-2025-53773 — checked 2026-11-13. No official agent-only CVE subset exists. Iris is not a CVE scanner — use only on exact product/version match.
* OWASP LLM Top 10 (2025) — mostly taxonomy. Index genai.owasp.org/llm-top-10/ — checked 2026-11-13. Metadata-clear only: LLM06 genai.owasp.org/llmrisk/llm062025-excessive-agency/, LLM10 genai.owasp.org/llmrisk/llm102025-unbounded-consumption/, partly LLM05 genai.owasp.org/llmrisk/llm052025-improper-output-handling/ and LLM03 as a pinned hash/version check. All others need bodies — Unknown. OWASP Agentic threats genai.owasp.org/resource/agentic-ai-threats-and-mitigations/ (17 Feb 2025, v1.0) — checked 2026-11-13 — same split: tool/identity/counter/exec metadata can be clear, semantic items cannot. T1–T15 names were read via a mirror, so treat as provisional — see Section 5.
* Prompt-injection lists — offline only. OWASP LLM01 genai.owasp.org/llmrisk/llm01-prompt-injection/, deepset huggingface.co/datasets/deepset/prompt-injections, AgentDojo github.com/ethz-spylab/agentdojo, garak github.com/NVIDIA/garak, LLM Guard github.com/protectai/llm-guard, Prompt Guard huggingface.co/meta-llama/Llama-Prompt-Guard-2-86M — all checked 2026-11-13. All need bodies or give a probability. Live hit = Unknown, ask human. Never engage.
* Domain/IP blocklists — the only feeds that match metadata directly. Spamhaus DBL www.spamhaus.org/blocklists/domain-blocklist/, URLhaus urlhaus.abuse.ch/about/, ThreatFox threatfox.abuse.ch/about/, ET Open rules.emergingthreats.net/open/ — checked 2026-11-13. Usable only as a human-pinned local mirror. Crowdsourced feeds can be poisoned. DNS/API lookup is a cloud query — prefer a local file. Feodo feodotracker.abuse.ch/about/ was empty at check — do not use.

## 3. Entries to add

Meaning: candidates for Charles/Adas to write in by hand. Iris adds none by itself. Format: destination / pattern — kind — why — source — date checked.

Safe sinks (only if user writes them in):

* 127.0.0.0/8 — loopback — stays on this machine — www.rfc-editor.org/rfc/rfc1122.txt — 2026-11-13
* ::1 — IPv6 loopback — stays on this machine — www.rfc-editor.org/rfc/rfc1122.txt — 2026-11-13
* localhost, *.localhost — local name — resolves to loopback — www.rfc-editor.org/rfc/rfc6761.txt — 2026-11-13
* IANA blocks with Globally Reachable = false (list each block at build time) — dead end — not reachable from internet — www.iana.org/assignments/iana-ipv4-special-registry/iana-ipv4-special-registry.xhtml — 2026-11-13

Detection only (never safe targets):

* api.openai.com — provider endpoint — real cloud destination, never mimic — developers.openai.com/api/reference/resources/beta/subresources/agents/methods/create — 2026-11-13
* api.anthropic.com — provider endpoint — same — platform.claude.com/docs/en/get-started — 2026-11-13
* generativelanguage.googleapis.com — provider endpoint — same — aistudio.google.com/docs/openai — 2026-11-13

Exploit clear-match rules (engage only on exact metadata match):

* ATT&CK T1700, T1567, T1041, T1048, T1071, T1059, T1105 on destination/protocol/tool — exfil, C2, exec, download — attack.mitre.org/resources/versions/ pin v20.1 — 2026-11-13
* KEV/NVD exact product+version match — known exploited flaw — www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json pin 2026.11.13 — 2026-11-13
* OWASP LLM06 tool+destination+scope beyond allowlist — too much agency — genai.owasp.org/llmrisk/llm062025-excessive-agency/ — 2026-11-13
* OWASP LLM10 rate/token/byte/loop counters over limit — unbounded use — genai.owasp.org/llmrisk/llm102025-unbounded-consumption/ — 2026-11-13
* OWASP LLM03 hash/version differs from pinned — supply chain — genai.owasp.org/llm-top-10/ — 2026-11-13
* OWASP LLM05 output routed to shell/SQL/eval/fetch sink in metadata — bad output handling — genai.owasp.org/llmrisk/llm052025-improper-output-handling/ — 2026-11-13
* Spamhaus DBL exact domain (local mirror, pinned) — bad domain — www.spamhaus.org/blocklists/domain-blocklist/ — 2026-11-13
* URLhaus / ThreatFox exact domain/IP (pinned, human-vetted) — malware/C2 — urlhaus.abuse.ch/about/ , threatfox.abuse.ch/about/ — 2026-11-13
* ET Open C2 subset exact IP/domain (pinned) — C2 — rules.emergingthreats.net/open/ — 2026-11-13
* Worked CVE examples only: CVE-2025-32711, CVE-2025-53773 — agent-adjacent flaws — services.nvd.nist.gov/rest/json/cves/2.0?cveId=CVE-2025-32711 — 2026-11-13

## 4. Entries to leave out, and why

* Any lookalike of a real provider — tricks the agent. Forbidden.
* mitmproxy docs.mitmproxy.org/stable/ — checked 2026-11-13 — MITM and body reading. Forbidden.
* Any auto-import from MCP registries or GitHub ecosystem bundles — listing is not safety approval, bundles too broad.
* Prompt-injection classifiers as live engage rules (deepset, garak, LLM Guard, Prompt Guard, AgentDojo live) — need bodies or give a score. Score = Unknown. Offline test use only.
* Semantic OWASP items as engage rules: LLM01, LLM02, LLM04, LLM07, LLM08, LLM09 and ATT&CK T1698 attack.mitre.org/techniques/T1698/, T1699 attack.mitre.org/techniques/T1699/ — cannot be proved from metadata. Unknown, ask human.
* Auto-updating feeds, live DNS/API blocklist lookups — poison risk, breaks local-only. Pinned local mirror only.
* Feodo Tracker — empty at check, 2026-11-13.
* CVE/KEV as a general traffic scanner — no product/version in metadata means no match.

## 5. Unresolved / next research

* Unresolved: "No collated DB exists anywhere" is not proven. Correct claim is "none found" in searches on 2026-11-13.
* Unresolved: OWASP Agentic T1–T15 wording from primary PDF genai.owasp.org/resource/agentic-ai-threats-and-mitigations/ — names came via an unofficial mirror. Re-fetch the PDF before codifying any T-rule. Any v1.1 / ASI01–ASI10 update also unverified.
* Unresolved: MITRE ATLAS technique IDs — atlas.mitre.org/ is script-rendered, AML.T0086 returned 404 on re-check, 2026-11-13. No ATLAS entries until the official data file is fetched.
* Unresolved: Whether CVE-2025-32711 / CVE-2025-53773 are in KEV — 1781-entry feed not fully parsed. Not claimed.
* Unresolved: TEST-NET dead ends (RFC 5737) — primary source not fetched. Not used.
* Unresolved: LLM Guard archived status, exact MCP/Docker/GitHub counts and digests, Squid domain-fronting limits, Feodo empty-temporary-or-dead — verify at build time and pin.
* Unresolved: Individual OWASP pages for LLM03, LLM04, LLM07, LLM08, LLM09 — titles verified from the index only.
* Next step for Charles: approve the home-built plan — Safe DB v1 = hand-written loopback only; Exploit DB v1 = pinned ATT&CK v20.1 + KEV 2026.11.13 + NVD snapshot + metadata-clear OWASP + pinned local blocklist mirrors — then do the primary re-fetches above so every entry ships with exact URL, version, and date.
