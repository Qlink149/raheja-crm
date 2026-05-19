import re
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ...core.database import get_db
from ...core.rbac import ROLE_ADMIN, ROLE_SALES
from ...core.security import get_current_user
from ...services.assignment_service import rep_lead_filter

router = APIRouter()

LEAD_PROJECTION = {
    "_id": 0,
    "id": 1,
    "full_name": 1,
    "first_name": 1,
    "last_name": 1,
    "project": 1,
    "mobile": 1,
    "mobile_digits": 1,
    "temperature": 1,
    "status": 1,
    "disposition": 1,
    "is_vip": 1,
    "assigned_to": 1,
    "assigned_to_name": 1,
    "sales_qualification": 1,
    "updated_at": 1,
}


def _build_leads_query(
    base_filter: dict,
    temperature: Optional[str] = None,
    search: Optional[str] = None,
) -> dict:
    query: dict = dict(base_filter)
    if temperature and temperature.lower() != "all":
        query["temperature"] = temperature
    if search and search.strip():
        q = re.escape(search.strip())
        search_clause = {
            "$or": [
                {"full_name": {"$regex": q, "$options": "i"}},
                {"first_name": {"$regex": q, "$options": "i"}},
                {"last_name": {"$regex": q, "$options": "i"}},
                {"project": {"$regex": q, "$options": "i"}},
                {"mobile": {"$regex": q, "$options": "i"}},
            ]
        }
        if query:
            query = {"$and": [query, search_clause]}
        else:
            query = search_clause
    return query


@router.get("")
async def get_my_dashboard(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    role = (current_user.get("role") or ROLE_SALES).lower()
    if role == ROLE_ADMIN:
        return {
            "rep_name": current_user.get("full_name"),
            "is_admin": True,
            "metrics": {},
            "message": "Admins use the main Dashboard for org-wide metrics.",
        }

    uid = current_user["id"]
    name = current_user["full_name"]
    base_filter = rep_lead_filter(uid, name)

    total_leads = await db.leads.count_documents(base_filter)
    hot = await db.leads.count_documents({**base_filter, "temperature": "Hot"})
    warm = await db.leads.count_documents({**base_filter, "temperature": "Warm"})
    cold = await db.leads.count_documents({**base_filter, "temperature": "Cold"})
    qualified = await db.leads.count_documents(
        {**base_filter, "sales_qualification": {"$nin": ["", None]}}
    )

    return {
        "rep_name": name,
        "is_admin": False,
        "metrics": {
            "total_leads": total_leads,
            "hot": hot,
            "warm": warm,
            "cold": cold,
            "qualified": qualified,
        },
    }


@router.get("/leads")
async def get_my_dashboard_leads(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    temperature: Optional[str] = None,
    search: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    role = (current_user.get("role") or ROLE_SALES).lower()
    if role == ROLE_ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Admins should use /api/leads for the full lead list.",
        )

    uid = current_user["id"]
    name = current_user["full_name"]
    base_filter = rep_lead_filter(uid, name)
    query = _build_leads_query(base_filter, temperature, search)

    total = await db.leads.count_documents(query)
    cursor = (
        db.leads.find(query, LEAD_PROJECTION)
        .sort("updated_at", -1)
        .skip(skip)
        .limit(limit)
    )
    leads = await cursor.to_list(limit)
    return {"leads": leads, "total": total, "skip": skip, "limit": limit}
