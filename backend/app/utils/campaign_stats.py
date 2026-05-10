"""Map Futwork webhook / call_history fields to campaign live_status bucket keys."""
from __future__ import annotations

from typing import Dict, Optional

# Mongo + API field names (snake_case)
LIVE_STATUS_DEFAULTS: Dict[str, int] = {
    "completed": 0,
    "busy": 0,
    "no_answer": 0,
    "call_disconnected": 0,
    "failed": 0,
}


def default_live_status() -> Dict[str, int]:
    return dict(LIVE_STATUS_DEFAULTS)


def _norm(s: str) -> str:
    return (s or "").strip().lower().replace("_", "-")


def map_futwork_raw_to_live_key(status_raw: str) -> Optional[str]:
    """Map payload top-level status string to live_status increment key."""
    s = _norm(status_raw)
    if not s:
        return None
    if s in ("completed",):
        return "completed"
    if s in ("busy",):
        return "busy"
    if s in ("no-answer", "noanswer"):
        return "no_answer"
    if s in ("call-disconnected", "calldisconnected"):
        return "call_disconnected"
    if s in ("failed", "call-failed", "callfailed"):
        return "failed"
    return None


DISPOSITION_KEY_MAP = {
    "interested":     "interested",
    "semi-interested": "semiInterested",
    "semi interested": "semiInterested",
    "semiinterested": "semiInterested",
    "not interested": "notInterested",
    "callback":       "callback",
    "busy":           "noAnswer",
    "no answer":      "noAnswer",
    "dropped":        "notInterested",
}


def map_disposition_to_key(disposition: Optional[str]) -> Optional[str]:
    """Map a free-text disposition to legacy `dispositions.*` bucket key."""
    if not disposition:
        return None
    return DISPOSITION_KEY_MAP.get(str(disposition).strip().lower())


# Raw Futwork lifecycle statuses we treat as terminal for a call/lead.
TERMINAL_RAW_STATUSES = frozenset(
    {"completed", "call-disconnected", "no-answer", "busy", "failed", "call-failed"}
)


def is_terminal_status(status_raw: Optional[str]) -> bool:
    return _norm(status_raw or "") in TERMINAL_RAW_STATUSES


def compute_inc_delta(prev_key: Optional[str], new_key: Optional[str]) -> Dict[str, int]:
    """Return a dict suitable for Mongo $inc that rebalances counters.

    - prev == new (including both None): no change.
    - prev None, new set: {new: +1}.
    - prev set, new None: {prev: -1}.
    - prev != new (both set): {new: +1, prev: -1}.
    """
    if prev_key == new_key:
        return {}
    delta: Dict[str, int] = {}
    if prev_key:
        delta[prev_key] = delta.get(prev_key, 0) - 1
    if new_key:
        delta[new_key] = delta.get(new_key, 0) + 1
    return delta


def map_stored_call_to_live_key(futwork_status: Optional[str], normalized_status: Optional[str]) -> Optional[str]:
    """Prefer futwork_status when present; else use normalized status from call_history.status."""
    if futwork_status and str(futwork_status).strip():
        k = map_futwork_raw_to_live_key(str(futwork_status))
        if k:
            return k
    s = _norm(str(normalized_status or ""))
    if s in ("completed",):
        return "completed"
    if s in ("busy",):
        return "busy"
    if s in ("no-answer", "noanswer"):
        return "no_answer"
    if s in ("failed",):
        return "failed"
    return None
