"""Devtool panel seam: human-only actions for the dev-only panel.

This module is dev only, never shipped in the consumer app. It holds
plain Python functions a human clicks in the local dev panel. There is
no HTTP route here and no remote caller: the panel button calls these
functions in the same local process that runs the watched proxy.

Every action reuses the proxy's existing machinery and reason
vocabulary. A new finger on the same human-only hand: no new gate,
no new outcome, no new verdict.
"""
from __future__ import annotations


def pause_run(state, trace_id: str, reason: str = "human pause") -> bool:
    """Pause one Run when the human presses the panel Pause button.

    Human only, local only. Delegates to the proxy's own pause, so the
    journal row comes first and the live tunnel is cut right after,
    exactly like a direct pause. Returns True when the Run is paused
    (or already was), False when the human gave no usable reason.
    """
    return state.pause_run(trace_id, reason=reason)
