# Who writes done

Date: 2026-11-13, 19:11 EST
Status: decided

## Problem
A verdict needs a definition of done. If the agent writes it, and checks it, that is a circle.

## Intention
Done had to be written first, approved by a human, and checkable by a read that could have failed.

## Options
Agent writes done, and checks it. Human writes done every time. Agent proposes, human approves, once per task type.

## Choice
Agent proposes, human approves, once per task type. Human in the loop.
Intent is automatic always. The agent writes intent plus an idempotency key before it acts, with no human per Run.
Journal first, since 2026-11-13, 14:04.

## Rejected
Agent writes done alone. That is the agent grading its own work.
Human writes done every time. That is slow, and it blocks every Run.
No approved done definition. Then the verdict is Unknown, not Correct. Automation without an approved done definition for a new task type is Unknown, not Correct.

## Links
Verdict rule: Correct means every clause of the human approved done definition was checked by a read that could have failed, and all passed. Incorrect means a clause was read and contradicted after settle time. Unknown means anything else.
