"""Lead resolution helpers for Futwork webhooks (unit-testable)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_lead_lookup_clauses(
    webhook_futwork_id: str,
    echo_client_id: str,
) -> List[Dict[str, Any]]:
    """Mongo $or clauses for matching a lead from webhook IDs."""
    clauses: List[Dict[str, Any]] = []
    if webhook_futwork_id:
        clauses.append({"futwork_lead_id": webhook_futwork_id})
    if echo_client_id:
        clauses.append({"client_lead_id": echo_client_id})
        clauses.append({"external_id": echo_client_id})
    return clauses


def lead_lookup_filter(clauses: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$or": clauses}


def lead_update_filter(existing_lead: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Mongo filter for updating a matched lead document."""
    if not existing_lead:
        return None
    lid = (existing_lead.get("id") or "").strip()
    if not lid:
        return None
    return {"id": lid}


def call_history_lead_id_value(
    existing_lead: Optional[Dict[str, Any]],
    *,
    echo_client_id: str = "",
    webhook_futwork_id: str = "",
) -> str:
    """Internal leads.id for call_history.lead_id when matched."""
    if existing_lead and (existing_lead.get("id") or "").strip():
        return str(existing_lead["id"]).strip()
    return ""
