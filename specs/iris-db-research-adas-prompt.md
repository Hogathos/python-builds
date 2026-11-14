# Iris DB research — prompt for Adas's agent

Run this in Muse Code, Wonder / smart model, high effort.
Check 5h + weekly usage first. Only run if Adas is okay with the cost.
Wonder is parallel multi-agent, expensive. Do not run if weekly is low.

## What Iris is, in one sentence

Iris is a local app that watches an AI agent, and stops it when it does something wrong.

Local only, metadata only, no MITM, no bodies, no keys, fail-closed, human in the loop, plain words.

## The two DBs — research only, no skeleton needed

Charles is building the skeletons himself. Just do the research parts.

1. Safe destinations DB
   - Where a redirected Run goes instead of a risky place: safe mirror, dead end, loopback.
   - Rules: user writes the list, Iris can suggest, Iris never invents a safe destination. Never redirect to a destination that looks like the real one to trick the agent.

2. Exploit DB
   - What Iris checks every Run against, in real time, metadata only.
   - Rules: clear rule match only = proactive engage (auto-redirect / pause / block, log, alert human, human can Undo). Probabilistic score alone = no engage, say Unknown, ask human. Never auto-update from an untrusted source.

## Research questions

1. Is there a collated DB of safe destinations for agent traffic? Check: official provider / vendor lists, loopback / local only, curated allowlists, MCP gateway safe lists, proxy safe lists.
2. Is there a collated DB of exploits that matter for agent traffic? Check: CVE records (agent-relevant only — Iris is not a CVE scanner), MITRE ATT&CK, OWASP LLM / agentic threats, prompt-injection pattern lists, tool-abuse / exfil pattern lists, public blocklists.
3. For each candidate source: is it verified, versioned, source + date per entry, maintained, open / free to use, no cloud required?
4. What entries go in, what stays out, and why? Give examples, in plain words, with source + date per entry.
5. If no collated DB exists for either one, say so plainly, and list what a home-built DB should be built from, versioned, with attribution.

## Rules for the report

- No guessed entries. Every entry needs source + date, verified. If no verified source, entry does not go in.
- No bodies, no keys, no MITM, no guessing.
- Cite every source, with exact URL, and date checked.
- Mark unresolved items as unresolved, do not fill them with a guess.
- Plain words, short enough to digest into writing. One section at a time.

## Deliverable

Markdown, in chat, to Adas — auto-generate the full markdown report in chat, so Adas can download / copy it and DM it to Charles. Do NOT push to GitHub.
Adas will send the markdown to Charles, Charles will file it himself.

Report structure:
1. Safe destinations — collated DBs found, or none found, with sources
2. Exploit DB — collated DBs found, or none found, with sources
3. Entries to add, with source + date per entry, in plain format — destination / pattern, kind, why safe / risky, source, date checked
4. Entries to leave out, and why
5. Unresolved / next research
