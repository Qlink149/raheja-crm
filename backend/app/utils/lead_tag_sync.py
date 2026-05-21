"""Keep CRM `status` and `temperature` aligned (independent of Futwork last_call_status)."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

# CRM statuses that should never show Hot/Warm temperature.
_COLD_STATUS_PATTERNS = (
    r"^non[\s-]*contactable$",
    r"^lost$",
    r"^dnc$",
    r"^do[\s-]*not[\s-]*call$",
    r"^not[\s-]*reachable$",
    r"^invalid[\s-]*number$",
    r"^wrong[\s-]*number$",
)

TERMINAL_FAIL_CALL_STATUSES = frozenset({
    "no-answer",
    "no_answer",
    "busy",
    "failed",
    "call-failed",
    "call-disconnected",
    "call_disconnected",
})


def _normalize_status_key(status: str) -> str:
    return re.sub(r"\s+", " ", (status or "").strip().lower())


def is_non_contactable_status(status: str) -> bool:
    key = _normalize_status_key(status)
    if not key:
        return False
    return any(re.match(pat, key) for pat in _COLD_STATUS_PATTERNS)


def temperature_for_status(status: str) -> Optional[str]:
    """Return canonical temperature when CRM status implies Cold."""
    if is_non_contactable_status(status):
        return "Cold"
    return None


def needs_cold_temperature_for_status(
    status: str,
    temperature: Any = None,
) -> bool:
    """True when CRM status requires Cold but temperature is missing or still Hot/Warm."""
    if not is_non_contactable_status(status):
        return False
    temp = "" if temperature is None else str(temperature).strip()
    return temp in ("", "Hot", "Warm")


def temperature_for_call_outcome(
    *,
    call_status: str,
    disposition: str = "",
) -> str:
    """
    Derive temperature from Futwork call outcome (not CRM status).
    Mirrors seed_call_history.get_temperature semantics.
    """
    d = (disposition or "").strip().lower()
    s = (call_status or "").strip().lower().replace("_", "-")

    if d in ("interested", "highly interested", "hot", "callback", "qualified"):
        return "Hot"
    if d in ("partially interested", "callback requested", "busy"):
        return "Warm"
    if d in ("not interested", "dnc", "dropped"):
        return "Cold"
    if s in TERMINAL_FAIL_CALL_STATUSES:
        return "Cold"
    if s == "completed":
        return "Warm"
    return "Cold"


def reconcile_temperature_with_status(
    lead_patch: Dict[str, Any],
    *,
    existing_temperature: str = "",
) -> Dict[str, Any]:
    """
    If CRM status is non-contactable-like, clear display tags (no Warm/Cold pill).
    """
    from .lead_qualification_tags import non_contactable_tag_patch

    out = dict(lead_patch)
    status = str(out.get("status") or "").strip()
    if is_non_contactable_status(status):
        out.update(non_contactable_tag_patch())
    return out


def apply_webhook_temperature_sync(
    lead_set: Dict[str, Any],
    *,
    existing_lead: Optional[Dict[str, Any]],
    incoming_terminal: bool,
    call_status: str,
    disposition: str = "",
) -> Dict[str, Any]:
    """
    After building webhook lead_set: sync temperature from CRM status or terminal call failure.
    Does not modify CRM `status`.
    """
    out = dict(lead_set)
    crm_status = str((existing_lead or {}).get("status") or "").strip()
    existing_temp = str((existing_lead or {}).get("temperature") or "").strip()

    status_patch = reconcile_temperature_with_status(
        {"status": crm_status, "temperature": out.get("temperature", existing_temp)},
        existing_temperature=existing_temp,
    )
    if status_patch.get("temperature"):
        out["temperature"] = status_patch["temperature"]
        return out

    if not incoming_terminal:
        return out

    normalized = (call_status or "").strip().lower().replace("_", "-")
    if normalized in TERMINAL_FAIL_CALL_STATUSES:
        if existing_temp in ("", "Hot", "Warm") or "temperature" not in out:
            out["temperature"] = "Cold"
        return out

    if normalized == "completed" and disposition:
        derived = temperature_for_call_outcome(
            call_status=normalized,
            disposition=disposition,
        )
        if derived and existing_temp in ("", "Hot", "Warm"):
            out["temperature"] = derived

    return out
