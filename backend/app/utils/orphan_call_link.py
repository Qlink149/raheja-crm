"""Link or create leads for orphan call_history rows (no lead_id)."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from ..core.time_utils import utc_now
from ..models.structured_extraction import UnifiedStructuredExtraction
from ..services.structured_ai_service import StructuredAIService
from .csv_processor import normalize_phone, phone_lookup_candidates
from .webhook_lead import lead_update_filter, resolve_lead_for_webhook

logger = logging.getLogger(__name__)

# Same-batch dedup when dry_run skips DB inserts (keyed by mobile_digits).
_dry_run_lead_cache: Dict[str, Dict[str, Any]] = {}
_DRY_RUN_LEAD_NS = uuid.UUID("a8f3c2e1-9b4d-4f6a-8c0d-1e2f3a4b5c6d")


def clear_dry_run_lead_cache() -> None:
    _dry_run_lead_cache.clear()


def structured_extraction_from_call(doc: Dict[str, Any]) -> Optional[UnifiedStructuredExtraction]:
    raw = doc.get("structured_extraction")
    if not isinstance(raw, dict) or not raw:
        return None
    try:
        return UnifiedStructuredExtraction.model_validate(raw)
    except Exception:
        return None


def _display_name_from_call(call_doc: Dict[str, Any], extraction: Optional[UnifiedStructuredExtraction]) -> str:
    if extraction and (extraction.lead_name or "").strip() not in ("", "Unknown"):
        return (extraction.lead_name or "").strip()
    name = (call_doc.get("customer_name") or "").strip()
    return name if name and name != "Unknown" else "Unknown"


async def create_lead_from_orphan_call(
    db,
    call_doc: Dict[str, Any],
    *,
    dry_run: bool = False,
) -> tuple[Optional[Dict[str, Any]], bool]:
    """
    Create a minimal CRM lead when Futwork called a number not present in `leads`.

    Uses stable client_lead_id FW-CALL-{mobile_digits} so repeat calls share one lead.

    Returns (lead_doc, is_new). is_new is False when an existing lead was reused.
    """
    mobile_digits = normalize_phone(
        str(call_doc.get("mobile_digits") or call_doc.get("phone") or "")
    )
    if len(mobile_digits) != 10:
        logger.warning(
            "Cannot create lead from orphan call: invalid phone | call_id=%s",
            call_doc.get("id"),
        )
        return None, False

    existing = await db.leads.find_one(
        {"mobile_digits": mobile_digits},
        {"_id": 0, "id": 1, "client_lead_id": 1, "assigned_user_id": 1},
    )
    if existing:
        return existing, False

    client_lead_id = f"FW-CALL-{mobile_digits}"
    dup = await db.leads.find_one(
        {"client_lead_id": client_lead_id},
        {"_id": 0, "id": 1, "client_lead_id": 1, "assigned_user_id": 1},
    )
    if dup:
        return dup, False

    if dry_run:
        cached = _dry_run_lead_cache.get(mobile_digits)
        if cached:
            return cached, False

    extraction = structured_extraction_from_call(call_doc)
    now = utc_now()
    lead_id = (
        str(uuid.uuid5(_DRY_RUN_LEAD_NS, client_lead_id))
        if dry_run
        else str(uuid.uuid4())
    )
    name = _display_name_from_call(call_doc, extraction)

    lead_doc: Dict[str, Any] = {
        "id": lead_id,
        "client_lead_id": client_lead_id,
        "mobile": str(call_doc.get("phone") or mobile_digits),
        "mobile_digits": mobile_digits,
        "full_name": name,
        "futwork_sync_status": "pushed",
        "source": "futwork_orphan_call",
        "status": "Inquiry",
        "temperature": "Warm",
        "created_at": now,
        "updated_at": now,
    }
    if call_doc.get("disposition"):
        lead_doc["disposition"] = call_doc["disposition"]
    if call_doc.get("transcript"):
        lead_doc["transcript"] = call_doc["transcript"]

    if extraction is not None:
        svc = StructuredAIService(db)
        patch = svc.to_db_lead_patch_unified(extraction)
        patch.pop("updated_at", None)
        lead_doc.update(patch)
        if patch.get("disposition"):
            lead_doc["disposition"] = patch["disposition"]

    if dry_run:
        _dry_run_lead_cache[mobile_digits] = lead_doc
        return lead_doc, True

    try:
        await db.leads.insert_one(lead_doc)
    except Exception:
        logger.exception(
            "Failed to insert lead from orphan call | call_id=%s | client_lead_id=%s",
            call_doc.get("id"),
            client_lead_id,
        )
        return None, False
    return lead_doc, True


async def resolve_or_link_orphan_call(
    db,
    call_doc: Dict[str, Any],
    *,
    create_missing: bool = False,
    dry_run: bool = False,
) -> tuple[Optional[Dict[str, Any]], str]:
    """
    Resolve lead for an orphan call_history row.

    Returns (lead_doc, reason) where reason is linked|created|skipped_*.
    """
    call_id = call_doc.get("id") or call_doc.get("call_sid") or ""
    raw_phone = call_doc.get("phone") or call_doc.get("to_number") or call_doc.get("mobile_digits") or ""
    echo_client = str(call_doc.get("client_lead_id") or "").strip()
    futwork_id = str(call_doc.get("futwork_lead_id") or "").strip()

    projection = {"_id": 0, "id": 1, "assigned_user_id": 1, "client_lead_id": 1}

    lead = await resolve_lead_for_webhook(
        db,
        webhook_futwork_id=futwork_id,
        echo_client_id=echo_client,
        raw_phone=raw_phone,
        projection=projection,
    )
    if lead and lead.get("id"):
        return lead, "linked_existing"

    candidates = phone_lookup_candidates(raw_phone)
    if not candidates:
        if create_missing:
            created, is_new = await create_lead_from_orphan_call(db, call_doc, dry_run=dry_run)
            if created:
                return created, "created_new" if is_new else "linked_existing"
        return None, "skipped_invalid_phone"

    if create_missing:
        created, is_new = await create_lead_from_orphan_call(db, call_doc, dry_run=dry_run)
        if created:
            return created, "created_new" if is_new else "linked_existing"

    return None, f"skipped_no_lead_in_db (tried {candidates})"


async def apply_orphan_call_link(
    db,
    call_doc: Dict[str, Any],
    lead: Dict[str, Any],
    *,
    dry_run: bool = False,
) -> bool:
    """Set call_history.lead_id and merge AI extraction onto the lead."""
    call_id = call_doc.get("id") or call_doc.get("call_sid") or ""
    lead_id = str(lead.get("id") or "")
    flt = lead_update_filter(lead)
    if not call_id or not flt:
        return False

    extraction = structured_extraction_from_call(call_doc)
    lead_patch: Dict[str, Any] = {}
    if extraction is not None:
        lead_patch = StructuredAIService(db).to_db_lead_patch_unified(extraction)

    if dry_run:
        return True

    await db.call_history.update_one({"id": call_id}, {"$set": {"lead_id": lead_id}})
    if lead_patch:
        await db.leads.update_one(
            flt,
            {"$set": lead_patch, "$unset": {"aiPersonaSummary": "", "strategicNextMove": ""}},
        )
    return True
