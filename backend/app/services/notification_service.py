"""Persisted in-app notifications (bell feed)."""
from __future__ import annotations

import re
import uuid
from typing import Any, Dict, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from ..core.time_utils import iso_utc_now, utc_now

from ..core.config import settings

CALLING_ENGINE_NAME = "Calling Engine"
WHITELABEL_AGENT_LABEL = settings.WHITELABEL_AGENT_DISPLAY_NAME

_SOURCE_LABELS = {
    "Futwork CSV Import": "Platform Pipeline",
    "futwork_orphan_call": "Inbound Call",
    "futwork": CALLING_ENGINE_NAME,
}


def map_lead_source_label(raw: Any) -> str:
    s = str(raw or "").strip()
    if not s:
        return "Direct"
    if s in _SOURCE_LABELS:
        return _SOURCE_LABELS[s]
    if re.search(r"futwork", s, re.IGNORECASE):
        return CALLING_ENGINE_NAME
    return s


def sanitize_notification_text(text: Any) -> str:
    if text is None:
        return ""
    s = str(text)
    s = re.sub(r"\bFutwork\s+Agent\b", WHITELABEL_AGENT_LABEL, s, flags=re.IGNORECASE)
    s = re.sub(r"\bFutwork\b", CALLING_ENGINE_NAME, s, flags=re.IGNORECASE)
    return s


def _lead_display_name(lead: Dict[str, Any]) -> str:
    name = (lead.get("full_name") or "").strip()
    if name:
        return name
    return f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()


async def create_notification(
    db: AsyncIOMotorDatabase,
    *,
    type: str,
    title: str,
    message: str,
    lead_id: str = "",
    lead_name: str = "",
    recipient_user_id: str,
    recipient_name: str = "",
    severity: str = "medium",
    urgency: str = "action_needed",
    assigned_to: Optional[str] = None,
    task_id: Optional[str] = None,
    dedupe_key: Optional[str] = None,
    extra_fields: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Insert a notification. Returns id, or None if dedupe_key already exists."""
    if dedupe_key:
        existing = await db.notifications.find_one({"dedupe_key": dedupe_key}, {"_id": 1})
        if existing:
            return None

    now_dt = utc_now()
    now_iso = iso_utc_now()
    clean_title = sanitize_notification_text(title)
    clean_message = sanitize_notification_text(message)
    doc: Dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "type": type,
        "title": clean_title,
        "message": clean_message,
        "lead_id": lead_id or "",
        "lead_name": lead_name or "",
        "recipient_user_id": recipient_user_id,
        "recipient_name": recipient_name or assigned_to or "",
        "assigned_to": assigned_to or recipient_name or "",
        "severity": severity,
        "urgency": urgency,
        "is_read": False,
        "created_at": now_iso,
        "created_at_dt": now_dt,
    }
    if task_id:
        doc["task_id"] = task_id
    if dedupe_key:
        doc["dedupe_key"] = dedupe_key
    if extra_fields:
        doc.update(extra_fields)

    await db.notifications.insert_one(doc)
    return doc["id"]


async def notify_new_lead_assigned(
    db: AsyncIOMotorDatabase,
    lead: Dict[str, Any],
    assignee_user_id: str,
    assignee_name: str,
) -> Optional[str]:
    lead_id = lead.get("id", "")
    name = _lead_display_name(lead)
    source = map_lead_source_label(lead.get("lead_source") or lead.get("source") or "Unknown")
    return await create_notification(
        db,
        type="new_lead_assigned",
        title="New Lead Assigned",
        message=f"Lead {name} has been assigned to you from {source}",
        lead_id=lead_id,
        lead_name=name,
        recipient_user_id=assignee_user_id,
        recipient_name=assignee_name,
        assigned_to=assignee_name,
        severity="low",
        urgency="info",
    )


async def notify_lead_transferred(
    db: AsyncIOMotorDatabase,
    lead: Dict[str, Any],
    to_user_id: str,
    to_name: str,
    from_name: str = "",
    notes: str = "",
) -> Optional[str]:
    lead_id = lead.get("id", "")
    name = _lead_display_name(lead)
    msg = f"{name} transferred from {from_name or 'another rep'}"
    if notes:
        msg += f". Notes: {notes}"
    return await create_notification(
        db,
        type="lead_transferred",
        title="Lead Transferred to You",
        message=msg,
        lead_id=lead_id,
        lead_name=name,
        recipient_user_id=to_user_id,
        recipient_name=to_name,
        assigned_to=to_name,
        severity="high",
        urgency="action_needed",
    )
