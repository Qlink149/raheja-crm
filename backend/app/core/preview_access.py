"""Virtual Customer preview-tier access control and lead redaction."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from .config import settings
from ..utils.futwork_disposition_stats import futwork_disposition_exact

PREVIEW_UPSELL_DETAIL = (
    "Virtual Customer preview limit reached. Contact the Clara team to unlock full access."
)


def is_vc_preview_tier() -> bool:
    return (settings.VC_ACCESS_TIER or "").lower() == "preview"


def is_vc_locked_tier() -> bool:
    return (settings.VC_ACCESS_TIER or "").lower() == "locked"


def preview_disposition() -> str:
    return settings.VC_PREVIEW_DISPOSITION or "Site Visit"


def site_visit_filters() -> Dict[str, Any]:
    disp = preview_disposition()
    esc = re.escape(disp)
    return {
        "disposition": disp,
        "_site_visit_or": {
            "$or": [
                {"disposition": {"$regex": f"^{esc}$", "$options": "i"}},
                {"ai_disposition": {"$regex": f"^{esc}$", "$options": "i"}},
            ]
        },
    }


def build_site_visit_query(
    service,
    search: Optional[str] = None,
    extra_filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Mongo query for Site Visit leads via lead document disposition fields."""
    filters = dict(extra_filters or {})
    filters.pop("disposition", None)
    base = service._build_leads_query(search, filters)
    site_visit_clause = site_visit_filters()["_site_visit_or"]
    if base:
        return {"$and": [base, site_visit_clause]}
    return site_visit_clause


def _site_visit_call_match() -> Dict[str, Any]:
    return futwork_disposition_exact(preview_disposition())


def mask_full_name(name: Optional[str]) -> str:
    raw = (name or "").strip()
    if not raw or raw.lower() in ("unknown", "null null", "null"):
        return "Unknown"
    parts = raw.split()
    if len(parts) == 1:
        token = parts[0]
        if len(token) <= 1:
            return f"{token}***"
        return f"{token[0]}***"
    first = parts[0]
    last = parts[-1]
    first_mask = f"{first[0]}***" if first else "***"
    last_mask = f"{last[0]}***" if last else "***"
    return f"{first_mask} {last_mask}"


def to_lead_teaser(doc: Dict[str, Any]) -> Dict[str, Any]:
    disp = (doc.get("disposition") or doc.get("ai_disposition") or preview_disposition()).strip()
    return {
        "id": doc.get("id", ""),
        "full_name": mask_full_name(doc.get("full_name")),
        "project": doc.get("project") or "",
        "location_category": doc.get("location_category") or "Other",
        "budget_category": doc.get("budget_category") or "Other",
        "qualification_category": (doc.get("qualification_category") or "").strip(),
        "disposition": disp,
        "is_locked": True,
    }


def _lead_service(db: AsyncIOMotorDatabase):
    from ..services.lead_service import LeadService

    return LeadService(db)


def _sales_filter_for_user(current_user: Optional[dict]) -> Optional[Dict[str, Any]]:
    if not current_user or (current_user.get("role") or "sales").lower() != "sales":
        return None
    from ..services.assignment_service import rep_lead_filter

    return rep_lead_filter(current_user["id"], current_user["full_name"])


async def _lead_matches_sales_scope(
    db: AsyncIOMotorDatabase,
    lead: Dict[str, Any],
    sales_filter: Optional[Dict[str, Any]],
) -> bool:
    if not sales_filter:
        return True
    lead_id = lead.get("id")
    if not lead_id:
        return False
    scoped = await db.leads.find_one(
        {"$and": [{"id": lead_id}, sales_filter]},
        {"_id": 0, "id": 1},
    )
    return scoped is not None


async def _ordered_site_visit_mobiles(
    db: AsyncIOMotorDatabase,
) -> List[str]:
    """Distinct Site Visit mobiles, newest call first (stable tie-break on mobile)."""
    pipeline = [
        {"$match": _site_visit_call_match()},
        {"$sort": {"started_at": -1, "created_at": -1}},
        {
            "$group": {
                "_id": "$mobile_digits",
                "latest_started": {"$first": "$started_at"},
                "latest_created": {"$first": "$created_at"},
            }
        },
        {"$sort": {"latest_started": -1, "latest_created": -1, "_id": 1}},
    ]
    docs = await db.call_history.aggregate(pipeline).to_list(None)
    return [str(d["_id"]).strip() for d in docs if d.get("_id")]


async def _get_site_visit_call_for_mobile(
    db: AsyncIOMotorDatabase,
    mobile: str,
) -> Optional[Dict[str, Any]]:
    return await db.call_history.find_one(
        {**_site_visit_call_match(), "mobile_digits": mobile},
        sort=[("started_at", -1), ("created_at", -1)],
    )


async def _is_preview_unlocked_mobile(
    db: AsyncIOMotorDatabase,
    mobile: str,
) -> bool:
    mobile = mobile.strip()
    if not mobile:
        return False
    ordered = await _ordered_site_visit_mobiles(db)
    limit = settings.VC_PREVIEW_UNLOCKED_LIMIT
    return mobile in set(ordered[:limit])


async def _resolve_lead_for_site_visit_call(
    db: AsyncIOMotorDatabase,
    call: Dict[str, Any],
    service,
) -> Optional[Dict[str, Any]]:
    """Find or create a CRM lead for a Site Visit call row."""
    from ..utils.orphan_call_link import (
        apply_orphan_call_link,
        create_lead_from_orphan_call,
    )

    lead_id = str(call.get("lead_id") or "").strip()
    mobile = str(call.get("mobile_digits") or "").strip()

    lead = None
    if lead_id:
        lead = await service.get_lead_by_id(lead_id)
    if not lead and mobile:
        lead = await db.leads.find_one({"mobile_digits": mobile}, {"_id": 0})
    if not lead:
        lead, _is_new = await create_lead_from_orphan_call(db, call)
        if lead and _is_new:
            await apply_orphan_call_link(db, call, lead)
    elif not lead_id and lead.get("id"):
        await apply_orphan_call_link(db, call, lead)

    if not lead:
        return None

    full = await service.get_lead_by_id(str(lead["id"]))
    return full or lead


async def _resolve_site_visit_leads_ordered(
    db: AsyncIOMotorDatabase,
    current_user: Optional[dict] = None,
) -> List[Dict[str, Any]]:
    """
    Unique leads with Site Visit outcomes.

    Primary source: call_history (matches dashboard Site Visit KPI).
    Creates minimal CRM leads for orphan calls so preview cards are clickable.
    Fallback: leads.disposition / leads.ai_disposition when no calls exist.
    """
    service = _lead_service(db)
    # Preview upsell shows the global Site Visit pipeline, not rep-scoped rows.
    sales_filter = None if is_vc_preview_tier() else _sales_filter_for_user(current_user)
    seen_ids: Set[str] = set()
    ordered: List[Dict[str, Any]] = []

    for mobile in await _ordered_site_visit_mobiles(db):
        call = await _get_site_visit_call_for_mobile(db, mobile)
        if not call:
            continue

        lead = await _resolve_lead_for_site_visit_call(db, call, service)
        if not lead:
            continue

        canonical_id = str(lead.get("id") or "").strip()
        if not canonical_id or canonical_id in seen_ids:
            continue
        if not await _lead_matches_sales_scope(db, lead, sales_filter):
            continue

        seen_ids.add(canonical_id)
        ordered.append(lead)

    if not ordered:
        lead_query = build_site_visit_query(service)
        if sales_filter:
            lead_query = (
                {"$and": [lead_query, sales_filter]}
                if lead_query
                else sales_filter
            )
        extra_cursor = (
            db.leads.find(lead_query, {"_id": 0})
            .sort("updated_at", -1)
            .limit(settings.VC_PREVIEW_UNLOCKED_LIMIT + settings.VC_PREVIEW_TEASER_LIMIT)
        )
        async for lead in extra_cursor:
            canonical_id = str(lead.get("id") or "").strip()
            if not canonical_id or canonical_id in seen_ids:
                continue
            seen_ids.add(canonical_id)
            ordered.append(lead)

    return ordered


async def get_preview_allowlist(
    db: AsyncIOMotorDatabase,
    current_user: Optional[dict] = None,
) -> Set[str]:
    limit = settings.VC_PREVIEW_UNLOCKED_LIMIT
    allowlist: Set[str] = set()
    for mobile in (await _ordered_site_visit_mobiles(db))[:limit]:
        lead = await db.leads.find_one(
            {"mobile_digits": mobile},
            {"_id": 0, "id": 1},
        )
        if lead and lead.get("id"):
            allowlist.add(str(lead["id"]))
    return allowlist


async def assert_lead_preview_access(
    db: AsyncIOMotorDatabase,
    lead_id: str,
    current_user: Optional[dict] = None,
) -> None:
    if not is_vc_preview_tier():
        return
    lead = await db.leads.find_one(
        {"id": lead_id},
        {"_id": 0, "id": 1, "mobile_digits": 1},
    )
    if not lead:
        raise HTTPException(status_code=403, detail=PREVIEW_UPSELL_DETAIL)
    mobile = str(lead.get("mobile_digits") or "").strip()
    if not mobile or not await _is_preview_unlocked_mobile(db, mobile):
        raise HTTPException(status_code=403, detail=PREVIEW_UPSELL_DETAIL)


def assert_vc_list_blocked() -> None:
    if is_vc_preview_tier():
        raise HTTPException(status_code=403, detail=PREVIEW_UPSELL_DETAIL)


def assert_vc_mutations_blocked() -> None:
    if is_vc_preview_tier():
        raise HTTPException(status_code=403, detail=PREVIEW_UPSELL_DETAIL)


async def fetch_preview_payload(
    db: AsyncIOMotorDatabase,
    current_user: Optional[dict] = None,
) -> Dict[str, Any]:
    unlocked_limit = settings.VC_PREVIEW_UNLOCKED_LIMIT
    teaser_limit = settings.VC_PREVIEW_TEASER_LIMIT

    all_leads = await _resolve_site_visit_leads_ordered(db, current_user)
    total = len(all_leads)
    unlocked_docs = all_leads[:unlocked_limit]
    teaser_docs = all_leads[unlocked_limit : unlocked_limit + teaser_limit]

    # Guard against dirty data in Mongo (e.g. numeric budget) causing response-model validation errors.
    for d in unlocked_docs:
        if isinstance(d, dict) and isinstance(d.get("budget"), (int, float)):
            d["budget"] = str(d["budget"])

    return {
        "unlocked": unlocked_docs,
        "locked_teasers": [to_lead_teaser(d) for d in teaser_docs],
        "meta": {
            "disposition_filter": preview_disposition(),
            "unlocked_limit": unlocked_limit,
            "total_matching": total,
            "locked_visible": len(teaser_docs),
        },
    }
