# DB automation — requirements

## What it does
Fetch pinned DB sources, parse exact matches only, draft entries with source + date + version per entry, to a draft file for human review. It does NOT add entries to the live DB on its own.

## Sources — pinned only
- MITRE ATT&CK v20.1, 13 Oct 2026 — techniques T1700, T1567, T1041, T1048, T1071, T1059, T1105
- CISA KEV feed 2026.11.13, 1781 entries, + NVD snapshot — exact product+version match only
- OWASP LLM Top 10 2025, metadata-clear only: LLM06, LLM10, LLM03 (hash/version), LLM05
- Spamhaus DBL, URLhaus, ThreatFox, ET Open C2 subset — exact domain/IP, pinned, local mirror only
- Safe sinks: 127.0.0.0/8, ::1, localhost / *.localhost, IANA blocks Globally Reachable = false

## Acceptance criteria
- Draft file lists each entry: destination / pattern, kind, why, source exact URL, date checked, version
- No entry without a verified source + date. No guessed entries.
- No lookalikes, no MITM sources, no auto-import from registries / GitHub bundles
- No prompt-injection classifiers as live rules, no semantic OWASP / T1698 / T1699 as engage rules
- No live DNS/API lookup at runtime, no auto-update from untrusted sources
- Offline fallback: local copy only, never guess a new entry
- Tests: pinned ATT&CK JSON parses T1700, draft contains source+date+version, a missing source produces Unknown / no entry, not a guess

## Non-goals
- Do NOT wire DBs into Steer / Control code. That waits for Part 2 + Control approval.
- Do NOT codify OWASP Agentic T1–T15 from a mirror, MITRE ATLAS, KEV status for CVE-2025-32711 / CVE-2025-53773, TEST-NET RFC 5737, or LLM03 from the index alone. Those need primary re-fetches first, see report §5.
- Do NOT change proxy, api, db, visualizer, or division_calculator behavior.

## Risks
- Invented entries, wrong source/date, unpinned versions, auto-add to live DB, MITM sources, score-as-verdict
