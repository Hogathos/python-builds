"""Run states for the devtool panel: a state machine, not effects.

Every Run shown in the panel sits in exactly one run state. Buttons act
only on states, never on raw rows: the Pause button is live in FLOWING
and quiet everywhere else. Verdicts ride alongside, never instead of,
the run state: a run with no read back is Unverified, explicitly.

States are Pause, Redirect, Red button, Verify, spend cap warn, spend
cap block, Unverified, Correct, Incorrect: named states, plain words,
no scores, no percentages.
"""
from __future__ import annotations

# Run states. FLOWING means traffic may move for this Run. VERIFY_OK
# means checked clean and waiting on a human to let it go again.
STATES = ("FLOWING", "PAUSED", "REDIRECTED", "STOPPED", "VERIFY_OK",
          "WARNED", "BLOCKED")

# Verdicts. Unverified is the honest default: a claim without a
# read back was never checked, so it is never Correct.
VERDICTS = ("Correct", "Incorrect", "Unverified")

# (state, event) -> next state. Every Steer action is a transition;
# nothing else moves a Run. Verify never unpauses by itself: only a
# human resume after a fresh Verify returns a Run to FLOWING, and that
# resume is journaled where it happens.
TRANSITIONS = {
    ("FLOWING", "pause"): "PAUSED",
    ("FLOWING", "redirect"): "REDIRECTED",
    ("FLOWING", "red_button"): "STOPPED",
    ("FLOWING", "cap_block"): "BLOCKED",
    ("FLOWING", "cap_warn"): "WARNED",
    ("PAUSED", "verify_ok"): "VERIFY_OK",
    ("PAUSED", "resume"): "FLOWING",
    ("PAUSED", "red_button"): "STOPPED",
    ("PAUSED", "cap_block"): "BLOCKED",
    ("REDIRECTED", "verify_ok"): "VERIFY_OK",
    ("REDIRECTED", "resume"): "FLOWING",
    ("REDIRECTED", "red_button"): "STOPPED",
    ("REDIRECTED", "cap_block"): "BLOCKED",
    ("STOPPED", "resume"): "FLOWING",
    ("VERIFY_OK", "resume"): "FLOWING",
    ("VERIFY_OK", "pause"): "PAUSED",
    ("VERIFY_OK", "redirect"): "REDIRECTED",
    ("VERIFY_OK", "red_button"): "STOPPED",
    ("VERIFY_OK", "cap_block"): "BLOCKED",
    ("VERIFY_OK", "cap_warn"): "WARNED",
    ("WARNED", "pause"): "PAUSED",
    ("WARNED", "redirect"): "REDIRECTED",
    ("WARNED", "red_button"): "STOPPED",
    ("WARNED", "verify_ok"): "VERIFY_OK",
    ("WARNED", "cap_block"): "BLOCKED",
    ("WARNED", "resume"): "FLOWING",
    ("BLOCKED", "verify_ok"): "BLOCKED",
    ("BLOCKED", "resume"): "FLOWING",
    ("BLOCKED", "red_button"): "STOPPED",
    ("BLOCKED", "cap_block"): "BLOCKED",
    ("BLOCKED", "pause"): "BLOCKED",
}


def _event_for(row) -> str | None:
    """Map one journal row onto a machine event, or None when the row
    moves nothing. Control rows are the events; traffic rows are not."""
    outcome = row["outcome"]
    reason = row["reason"] or ""
    if outcome == "paused" and "cap block" in reason:
        return "cap_block"
    if outcome == "paused":
        return "pause"
    if outcome == "redirected":
        return "redirect"
    if outcome == "stopped":
        return "red_button"
    if outcome == "warned":
        return "cap_warn"
    if outcome == "verified" and row["status"] == "success":
        return "verify_ok"
    if outcome == "" and reason in ("retry allowed after verify",
                                    "cap lifted",
                                    "verify ok"):
        return "resume"
    return None


def run_state(rows) -> str:
    """Fold one Run's journal rows, oldest first, into one run state.

    Pure function of the rows: same journal always gives the same state.
    A Run with no control row in its journal is FLOWING.
    """
    state = "FLOWING"
    for row in rows:
        event = _event_for(row)
        if event is not None:
            state = TRANSITIONS.get((state, event), state)
    return state


def verdict_for(rows) -> str:
    """One verdict per Run: the latest Verify verdict, else Unverified.

    A claim without a read back was never checked, so the honest
    default is Unverified, never Correct.
    """
    for row in reversed(list(rows)):
        if row["outcome"] == "verified":
            if row["status"] == "success":
                return "Correct"
            if row["status"] == "failure":
                return "Incorrect"
    return "Unverified"


def next_step(state: str, verdict: str) -> str:
    """One plain-words next step for a Run, from its state and verdict."""
    if state == "FLOWING" and verdict == "Unverified":
        return "Run is flowing, nothing checked yet. Verify it, or pause it to look."
    if state == "VERIFY_OK":
        return "Run checked clean. A human can let it go again."
    if state == "FLOWING":
        return "Run is flowing and its last check passed. Keep watching."
    if state == "PAUSED":
        return "Run is paused. Verify it, then a human can let it go again."
    if state == "REDIRECTED":
        return "Run now goes to its safe destination. Verify it there."
    if state == "STOPPED":
        return "Run is stopped. It stays stopped until a human says otherwise."
    if state == "WARNED":
        return ("Money spent at 80% of cap. Run continues. "
                "Watch spend and prepare to pause if it reaches the cap.")
    if state == "BLOCKED":
        return ("Run blocked at 100% of cap. "
                "Verify it, then a human must unblock it before it flows again.")
    return "Run state unknown. Ask a human before it moves again."


def pause_button_live(state: str) -> tuple:
    """Whether the Pause button is live for a Run in this state, and why
    in plain words when it is not. The button never pauses twice."""
    if state == "FLOWING":
        return True, "Pause this Run now."
    if state == "WARNED":
        return True, "Money spent at 80% of cap, run continues"
    if state == "BLOCKED":
        return (False,
                "Blocked at 100% of cap, a human must check it again, "
                "then unblock after Verify")
    if state == "VERIFY_OK":
        return False, "Run is checked clean, waiting for a human to let it go."
    if state in STATES:
        return False, "Run is stopped or paused, so the Pause button rests."
    return False, "Run state unknown, so the Pause button rests."
