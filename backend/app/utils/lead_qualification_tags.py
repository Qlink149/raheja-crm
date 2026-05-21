"""Canonical lead tags: qualification_category hierarchy + VIP flags; clear legacy temperature."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from ..services.structured_ai_service import qualification_category_from_matches
from .lead_tag_sync import is_non_contactable_status

_VIP_BUDGET_TIERS = frozenset({"5 Cr+", "2-5 Cr"})
_VALID_QC = frozenset({"Qualified", "VIP Pipeline", "Hot", "Cold", "Dormant"})


def _as_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("true", "1", "yes"):
            return True
        if s in ("false", "0", "no"):
            return False
    return None


def has_match_flags(lead: Dict[str, Any]) -> bool:
    """True if at least one match flag is explicitly set on the lead."""
    for key in ("budget_match", "area_match", "timeline_match"):
        if _as_bool(lead.get(key)) is not None:
            return True
    return False


def expected_qualification_category(lead: Dict[str, Any]) -> Optional[str]:
    if not has_match_flags(lead):
        return None
    return qualification_category_from_matches(
        bool(lead.get("budget_match")),
        bool(lead.get("area_match")),
        bool(lead.get("timeline_match")),
    )


def vip_flags_from_qualification(
    qualification_category: str,
    budget_category: str = "",
) -> Tuple[bool, bool, str]:
    qc = (qualification_category or "").strip()
    bc = (budget_category or "").strip()
    is_vip = qc in ("VIP Pipeline", "Qualified") or bc in _VIP_BUDGET_TIERS
    is_hni = bc == "5 Cr+"
    vip_category = "VIP/HNI" if is_vip else ""
    return is_vip, is_hni, vip_category


def non_contactable_tag_patch() -> Dict[str, Any]:
    """Clear all display tags for non-contactable CRM status."""
    return {
        "temperature": "",
        "qualification_category": "",
        "is_vip": False,
        "is_hni": False,
        "vip_category": "",
    }


def canonical_lead_tags_from_doc(
    lead: Dict[str, Any],
    *,
    lead_patch: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build $set fields for canonical tags from a lead document (and optional patch overlay).

    - Non-contactable: clear temperature + qualification_category + VIP flags.
    - Else with match flags: recompute qualification_category, clear temperature, refresh VIP.
    - Returns empty dict if no match flags and not non-contactable (caller may skip).
    """
    merged = {**lead, **(lead_patch or {})}
    status = str(merged.get("status") or "").strip()

    if is_non_contactable_status(status):
        return non_contactable_tag_patch()

    if not has_match_flags(merged):
        return {}

    qc = qualification_category_from_matches(
        bool(merged.get("budget_match")),
        bool(merged.get("area_match")),
        bool(merged.get("timeline_match")),
    )
    is_vip, is_hni, vip_cat = vip_flags_from_qualification(
        qc,
        str(merged.get("budget_category") or ""),
    )
    return {
        "qualification_category": qc,
        "temperature": "",
        "is_vip": is_vip,
        "is_hni": is_hni,
        "vip_category": vip_cat,
    }


def apply_canonical_tags_to_lead_patch(
    lead_patch: Dict[str, Any],
    lead: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge canonical tags into an outbound lead patch (webhook/scripts)."""
    out = dict(lead_patch)
    canonical = canonical_lead_tags_from_doc(lead, lead_patch=out)
    if canonical:
        out.update(canonical)
    elif is_non_contactable_status(str(lead.get("status") or out.get("status") or "")):
        out.update(non_contactable_tag_patch())
    return out
