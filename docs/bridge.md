# CyberHog <-> Muse Code bridge

Fingerprint: CYBERHOG-BRIDGE-2026-11-13-IRIS
Do not delete this header. This file is the shared mailbox between CyberHog (Main) and Muse Code (PyCharm). Charles is the courier only when a push is needed — otherwise each side reads / writes this file.

Rules:
- CyberHog writes prompts under "FROM CYBERHOG" with date/time EST.
- Muse Code writes reports under "FROM MUSE CODE" with date/time EST, commit hash, push result, test results.
- One prompt per task. No drip-feed.
- Co-Work Mode is ON for Iris / python-builds only. Muse Code MAY commit and push itself.
- Safeguards, always: stage named files only, never git add -A, never git commit -a, never commit .exe, dist/, build/, attempts.db, *.db, .pytest_cache/, *.spec, secrets.
- Scope: Iris / python-builds only. NOT assessed coursework, Academy, or client-data work — study-buddy rule still holds there.
- Charles reviews the diff on GitHub after.

## FROM CYBERHOG

<!-- CyberHog: paste the next prompt here, dated. Muse Code: read the latest entry, do it, report below. -->

## FROM MUSE CODE

<!-- Muse Code: paste your report here, dated, with commit hash, push result, test results. CyberHog reads it from GitHub. -->
