# Security

Iris is a local app. It runs on your own Windows machine, and it stays there.

## What Iris does

- It watches agent traffic on your machine, in plain words.
- It can pause one run, redirect one run, or block a network.
- It shows cost, in plain words.
- It keeps a log, on your machine, in SQLite.

## What Iris does not do

- It does not send your data to the cloud.
- It does not log message bodies, headers, or keys.
- It does not decrypt TLS. A CONNECT tunnel is a raw relay. Iris counts bytes, it does not read inside.
- It does not run on its own. A human starts it, a human stops it.
- It does not change its own rules in secret. Policy is a file you can read.

## How it stays safe

- Local only. Iris listens on 127.0.0.1, your machine only. No one else on the internet can reach it.
- Human in the loop. Iris never pauses, blocks, or redirects on its own. You do it, or a rule you wrote does it.
- Fail closed. If Iris stops, or the policy is missing, traffic stops. It never keeps going on a stale rule.
- Every action is logged. Who did it, what they did, when, which run, why. In plain words.
- Least privilege. Iris runs as you, not as admin. It can only touch its own proxy, its own log, its own dashboard.

## If you find a problem

Tell us. Open an issue on GitHub, or email charlesbrugh24@gmail.com.

Say what happened, in plain words. What you did, what Iris did, what you expected.

We will fix it, and we will say what we fixed.

## What Iris is not

Iris is not malware. It is not a spy tool. It does not hide what it does.

The code is public. You can read it. If you do not trust it, do not run it. That is the whole point.
