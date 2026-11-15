# Remote read back credential Default Do Not

Author: Hogathos
Decided by: human
Written by: human
Filed by: CyberHog, agent, filing and formatting only
AI written: no
Human written: yes
Tags: human-written, human-decided


Date: 2026-11-14
Status: decided

## Problem
To verify a remote effect, Iris has to read it back. To read it back, Iris may need a credential. A credential in Iris is a risk.

## Intention
Remote effects stay Unknown unless local proves them. No credential by default. No credential logged, ever.

## Options
Default yes, store a credential. Default no, read back only what is public. Opt in later, read only, in the OS credential store.

## Choice
Default is Do Not. V1 uses public read and human confirm. Opt in read only credential later, explicit Check only, never logged, not v1. Cost if default needed is Unknown, capped line item in the completion report unless approved in writing.

## Rejected
Default yes. That puts a credential in Iris by default, for a read that may not be needed.
Agent read back. Agent read back is basically no. Human paste only as a fallback.

## Links
Claims channel order: loopback gateway first, optional SDK or emitter second and thin, read back always. Part 2 landed Nov 14. It covers the loopback gateway, the optional SDK, what does not work, and credential free remote read back. It found no standard for that last one.
