# Prompt adaptation template

Authorship: human approved, agent drafted
Written by: agent, from Charles decisions, Nov 14-15, 2026
AI written: yes, as an instruction template, not as a decision
Human written: no, for this file only, decisions in graphs/ are human written


Use this order, for every feature, in one prompt per task, in Main first, then one clean spec prompt to Muse Code. Layered sequences of loops, not a single prompt.

## 1. Problem
One sentence. What is broken, or missing, in plain words.

## 2. Intention and done
Write the done definition first. Agent proposes, Charles approves, once per task type. Human in the loop.
Every clause checkable by a read that could have failed. No approved done means Unknown, not Correct.
Intent is automatic always. The agent writes intent plus an idempotency key before it acts, with no human per Run. Journal first.

## 3. Research
Look first. Memory, then files, then web with source and date, then live check. Name the tool, not a made up stack. Source first, gloss second, separated. Draft only what evidence supports, flag the rest as Unknown, with the next check named.

## 4. Experiments
Smallest test first. Write the failing test first, show it, Charles reviews the test, then implement. New behavior only, not refactors.

## 5. Method
Build, then verify by read back after settle time, from a source that could have failed, then steer.
Pause one Run. Red button all stop. Redirect one Run. Spend caps, warn 80 percent, block 100 percent.
Verdict: Correct, Incorrect, Unknown. Unknown means hold, ask a human.
Swarm risky states first, money, data, access. Sample the rest. Never claim all possible states.

## 6. Decisions
Date, choice, rejected alternative, and why. File in graphs/ and in the spec, so the same thing is not re-decided in a new chat.

## 7. Trajectory
What happened. What changed. What is still open.

## Rules that always stay
Plan gate for 2 or more modules: plan first, no code yet, files, order, risks, out of scope. Charles approves the plan, then a second prompt implements it. Small tasks skip the gate.
Spec file in specs/<feature>/requirements.md: what it does, acceptance criteria, non-goals, a few hundred words max. No implementation detail in the spec.
After implementation: one review prompt naming specific risks, security, edge cases, efficiency, not a generic review this.
Co-Work safeguards: stage named files only, never git add -A, never git commit -a, never commit .exe, dist/, build/, attempts.db, *.db, .pytest_cache/, *.spec, secrets. Report commit hash, push result, and test results.
Keep verbose comments and docstrings. They are part of the code, not slop.
Study buddy rule: reflective mirror, never an answer key, for coursework and assessed work.
Do not use Linear for Iris. Solo. GitHub Issues plus specs/ already does it. Revisit only with a team, or a second user filing issues.
Flywheel is a view for decision graphs, public link, beta, hosted. Repo graphs/ is the source of truth.

## Source
Ian Lapham, Andrew Pignanelli, Alex Fazio, Nov 14, 2026. Top engineers stopped reading code and went up an abstraction level. Focus is to build better systems to verify the impacts and delivery of changes, not just tests. Mock the state machine, swarm states, compare intention to presentation, monitor change automatically. One level above code.
