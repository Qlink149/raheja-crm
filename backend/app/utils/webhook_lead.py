"""Lead resolution helpers for Futwork webhooks (unit-testable)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .csv_processor import phone_lookup_candidates

logger = logging.getLogger(__name__)


def client_id_lookup_filter(echo_client_id: str) -> Optional[Dict[str, Any]]:
    """Mongo filter for CRM client id (recipientData echo). Priority 1."""
    cid = (echo_client_id or "").strip()
    if not cid:
        return None
    return {"$or": [{"client_lead_id": cid}, {"external_id": cid}]}


def futwork_id_lookup_filter(webhook_futwork_id: str) -> Optional[Dict[str, Any]]:
    """Mongo filter for Futwork platform lead id (top-level leadId). Priority 2."""
    fid = (webhook_futwork_id or "").strip()
    if not fid:
        return None
    return {"futwork_lead_id": fid}


def has_webhook_id_hints(webhook_futwork_id: str, echo_client_id: str) -> bool:
    return bool(client_id_lookup_filter(echo_client_id) or futwork_id_lookup_filter(webhook_futwork_id))


def build_lead_lookup_clauses(
    webhook_futwork_id: str,
    echo_client_id: str,
) -> List[Dict[str, Any]]:
    """Legacy flat $or clauses (logging only). Prefer sequential resolve_lead_by_webhook_ids."""
    clauses: List[Dict[str, Any]] = []
    client_flt = client_id_lookup_filter(echo_client_id)
    if client_flt:
        if "$or" in client_flt:
            clauses.extend(client_flt["$or"])
        else:
            clauses.append(client_flt)
    futwork_flt = futwork_id_lookup_filter(webhook_futwork_id)
    if futwork_flt:
        clauses.append(futwork_flt)
    return clauses


def lead_lookup_filter(clauses: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$or": clauses}


async def resolve_lead_by_webhook_ids(
    db,
    *,
    webhook_futwork_id: str,
    echo_client_id: str,
    projection: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Resolve lead by webhook IDs with explicit priority:
    1) client_lead_id / external_id (recipientData echo)
    2) futwork_lead_id (top-level leadId)
    """
    proj = projection or {
        "id": 1,
        "last_call_status_raw": 1,
        "last_call_status": 1,
        "futwork_lead_id": 1,
    }

    client_flt = client_id_lookup_filter(echo_client_id)
    if client_flt:
        lead = await db.leads.find_one(client_flt, proj)
        if lead:
            return lead

    futwork_flt = futwork_id_lookup_filter(webhook_futwork_id)
    if futwork_flt:
        lead = await db.leads.find_one(futwork_flt, proj)
        if lead:
            return lead

    return None


async def resolve_lead_by_phone_candidates(
    db,
    raw_phone: str,
    *,
    projection: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Match a single lead by mobile_digits variants (after ID lookup failed)."""
    candidates = phone_lookup_candidates(raw_phone)
    if not candidates:
        return None

    proj = projection or {
        "id": 1,
        "last_call_status_raw": 1,
        "last_call_status": 1,
        "futwork_lead_id": 1,
        "assigned_user_id": 1,
    }

    matches = await db.leads.find(
        {"mobile_digits": {"$in": candidates}},
        proj,
    ).to_list(5)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        logger.warning(
            "Ambiguous phone candidate match | candidates=%s | count=%s",
            candidates,
            len(matches),
        )
    return None


async def resolve_lead_for_webhook(
    db,
    *,
    webhook_futwork_id: str,
    echo_client_id: str,
    raw_phone: str,
    projection: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Full resolution: phone first (Raheja), then optional ID echoes (legacy)."""
    lead = await resolve_lead_by_phone_candidates(
        db,
        raw_phone,
        projection=projection,
    )
    if lead:
        return lead
    return await resolve_lead_by_webhook_ids(
        db,
        webhook_futwork_id=webhook_futwork_id,
        echo_client_id=echo_client_id,
        projection=projection,
    )


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
