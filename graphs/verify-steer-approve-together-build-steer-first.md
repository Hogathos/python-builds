# Verify and Steer approve together, build Steer first

Date: 2026-11-14
Status: decided, approval pending in words

## Problem
Verify and Steer touch control. A control endpoint, added early, could be used wrong, or used by the wrong thing.

## Intention
Approve Verify and Steer together, then build Steer first, then Verify. No control endpoint before the human says yes in words.

## Options
Build Verify first. Build Steer first. Build both at once. Add a control endpoint now.

## Choice
Approve together. Build Steer first, pause one Run, red button all stop, redirect one Run. Then build Verify. Then app mode. Then a second live workflow.

## Rejected
Add a control endpoint before approval. Do not add a control endpoint before Charles says yes in words.
Build Verify first. Steer is the stop. A stop has to exist before a verdict can act on it.

## Links
Part 2, section 8, ten decisions. Steer design file: iris-steer-design.md. Pause one Run, redirect one Run, red button all stop plus per network, all stop overrides. In flight pause cuts the tunnel, outcome Unknown, Verify before retry. Spend caps per project, warn 80 percent, block 100 percent.
