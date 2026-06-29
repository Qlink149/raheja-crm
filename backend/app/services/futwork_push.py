"""Shared Futwork platform lead push (single HTTP POST per lead)."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

import httpx

from ..core.config import settings

logger = logging.getLogger(__name__)


def ten_digit_phone(lead: Dict[str, Any]) -> str:
    """Last 10 digits for Futwork dial-out and Raheja lead identity."""
    raw_phone = (
        lead.get("recipientPhoneNumber")
        or lead.get("mobile_digits")
        or lead.get("mobile", "")
    )
    phone = "".join(c for c in str(raw_phone) if c.isdigit())[-10:]
    if len(phone) == 10:
        return phone
    db_digits = "".join(c for c in str(lead.get("mobile_digits") or "") if c.isdigit())[-10:]
    return db_digits if len(db_digits) == 10 else ""


def futwork_recipient_data(_lead: Dict[str, Any], customer_name: str) -> Dict[str, str]:
    """Raheja push: name only — mobile is the correlation key via recipientPhoneNumber."""
    return {"customer_name": customer_name}


def extract_futwork_lead_id(body: Any) -> str:
    """Best-effort scrape of the lead id Futwork returns after a successful push."""
    if not isinstance(body, dict):
        return ""
    for key in ("leadId", "lead_id", "id", "_id"):
        val = body.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    for wrapper in ("data", "lead", "result"):
        inner = body.get(wrapper)
        if isinstance(inner, dict):
            fid = extract_futwork_lead_id(inner)
            if fid:
                return fid
    return ""


def futwork_leads_endpoint() -> str:
    return (
        f"https://platform.futwork.ai/api/campaigns/"
        f"{settings.FUTWORK_CAMPAIGN_ID}/leads"
    )


def futwork_request_headers() -> Dict[str, str]:
    return {
        "x-api-key": settings.FUTWORK_API_KEY,
        "Content-Type": "application/json",
    }


def display_name_for_lead(lead: Dict[str, Any]) -> str:
    return (
        (lead.get("full_name") or "").strip()
        or (lead.get("customer_name") or "").strip()
        or "Unknown"
    )


async def post_one_lead_to_futwork(
    http_client: httpx.AsyncClient,
    db,
    lead: Dict[str, Any],
    *,
    campaign_id: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """
    POST one lead to Futwork and update futwork_sync_status in Mongo.

    Returns (success, futwork_lead_id or None).
    """
    from .lead_service import LeadService

    ls = LeadService(db)
    phone = ten_digit_phone(lead)
    if len(phone) != 10:
        logger.warning(
            "Skipping lead: invalid phone for Futwork dial | mobile_digits=%s",
            lead.get("mobile_digits"),
        )
        return False, None

    name = display_name_for_lead(lead)
    payload = {
        "recipientPhoneNumber": phone,
        "recipientData": futwork_recipient_data(lead, name),
    }
    endpoint = futwork_leads_endpoint()
    headers = futwork_request_headers()

    try:
        logger.info("FUTWORK PUSH REQUEST | URL: %s | Payload: %s", endpoint, payload)
        response = await http_client.post(endpoint, json=payload, headers=headers)
        logger.info(
            "FUTWORK PUSH RESPONSE | Status: %s | Body: %s",
            response.status_code,
            response.text,
        )
        response.raise_for_status()
        try:
            body = response.json()
        except Exception:
            body = None
        futwork_lead_id = extract_futwork_lead_id(body)
        await ls.apply_lead_futwork_sync(
            mobile_digits=phone,
            status="pushed",
            futwork_lead_id=futwork_lead_id or None,
            campaign_id=campaign_id,
        )
        return True, futwork_lead_id or None
    except httpx.HTTPStatusError as e:
        logger.error(
            "Failed to push lead %s to Futwork | HTTPStatusError: %s | Response Body: %s",
            phone,
            e,
            e.response.text if e.response else "",
            exc_info=True,
        )
        await ls.apply_lead_futwork_sync(
            mobile_digits=phone,
            status="failed",
            campaign_id=campaign_id,
        )
        return False, None
    except Exception as e:
        logger.error("Failed to push lead %s to Futwork: %s", phone, e, exc_info=True)
        await ls.apply_lead_futwork_sync(
            mobile_digits=phone,
            status="failed",
            campaign_id=campaign_id,
        )
        return False, None
