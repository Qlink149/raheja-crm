from fastapi import APIRouter, Depends, Query
from typing import Optional, Any, Dict, List
from datetime import datetime, timedelta
from ...core.database import get_db
from ...models.stats import DashboardStats
from .analytics import (
    _is_invalid_rep_name,
    _merge_query_with_valid_projects,
    _rep_name_expression,
)

router = APIRouter()

_AI_INTERESTED = ("Hot Lead", "Semi-Interested", "Semi-interested", "Mildly interested")
_VIP_BUDGET_TIERS = ("5 Cr+", "2-5 Cr")


def _legacy_qualified_positive() -> Dict[str, Any]:
    """Signals that map a legacy lead to Qualified (used inside $nor / $and)."""
    return {
        "$or": [
            {"status": "Qualified"},
            {"ai_disposition": {"$in": list(_AI_INTERESTED)}},
        ]
    }


def _legacy_vip_positive() -> Dict[str, Any]:
    """VIP legacy without temperature Hot (avoids overlap with Hot bucket)."""
    return {
        "$or": [
            {"is_vip": True},
            {"budget_category": {"$in": list(_VIP_BUDGET_TIERS)}},
        ]
    }


def _missing_qualification_clause() -> Dict[str, Any]:
    return {
        "$or": [
            {"qualification_category": {"$exists": False}},
            {"qualification_category": None},
            {"qualification_category": ""},
        ]
    }


def _qc_or_legacy(base: dict, category: str, legacy_match: Dict[str, Any]) -> dict:
    """
    Count leads in one qualification bucket.

    When ``qualification_category`` is set, only that explicit value counts.
    Legacy fallbacks apply only if QC is missing/empty; legacy rules are mutually
    exclusive (priority: Lost→Dormant, then Qualified, VIP by budget/is_vip, Hot, Cold).
    """
    return {
        **base,
        "$or": [
            {"qualification_category": category},
            {"$and": [_missing_qualification_clause(), legacy_match]},
        ],
    }


def _legacy_qualified_match() -> Dict[str, Any]:
    """Legacy Qualified after Dormant: not Lost, then Qualified status or interested AI."""
    return {
        "$and": [
            {"status": {"$ne": "Lost"}},
            _legacy_qualified_positive(),
        ]
    }


def _legacy_vip_match() -> Dict[str, Any]:
    """Legacy VIP after Qualified: not Lost, not Qualified signals, is_vip or premium budget."""
    return {
        "$and": [
            {"status": {"$ne": "Lost"}},
            {"$nor": [_legacy_qualified_positive()]},
            _legacy_vip_positive(),
        ]
    }


def _legacy_hot_match() -> Dict[str, Any]:
    """Legacy Hot: temperature Hot, excluding Lost, Qualified, VIP budget/is_vip."""
    return {
        "$and": [
            {"temperature": "Hot"},
            {"status": {"$ne": "Lost"}},
            {"$nor": [_legacy_qualified_positive()]},
            {"is_vip": {"$ne": True}},
            {"budget_category": {"$nin": list(_VIP_BUDGET_TIERS)}},
        ]
    }


def _legacy_cold_match() -> Dict[str, Any]:
    """Legacy Cold: temperature Cold, not Lost, not Qualified/VIP by legacy signals."""
    return {
        "$and": [
            {"temperature": "Cold"},
            {"status": {"$ne": "Lost"}},
            {"$nor": [_legacy_qualified_positive()]},
            {"is_vip": {"$ne": True}},
            {"budget_category": {"$nin": list(_VIP_BUDGET_TIERS)}},
        ]
    }


def _dormant_bucket_query(base: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dormant: explicit QC Dormant or legacy Lost with missing QC.
    """
    return {
        **base,
        "$or": [
            {"qualification_category": "Dormant"},
            {"$and": [_missing_qualification_clause(), {"status": "Lost"}]},
        ],
    }


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    project: Optional[str] = None,
    days: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db=Depends(get_db),
):
    base_query: Dict[str, Any] = {}
    if project and project != "all":
        base_query["project"] = project

    if days:
        cutoff = datetime.utcnow() - timedelta(days=days)
        base_query["created_at"] = {"$gte": cutoff}
    elif start_date or end_date:
        date_filter: Dict[str, Any] = {}
        if start_date:
            try:
                date_filter["$gte"] = datetime.strptime(start_date, "%Y-%m-%d")
            except ValueError:
                pass
        if end_date:
            try:
                date_filter["$lte"] = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            except ValueError:
                pass
        if date_filter:
            base_query["created_at"] = date_filter

    def merge(extra: dict) -> dict:
        return {**base_query, **extra}

    total_leads = await db.leads.count_documents(base_query)

    qualified_leads = await db.leads.count_documents(
        _qc_or_legacy(base_query, "Qualified", _legacy_qualified_match())
    )
    vip_pipeline = await db.leads.count_documents(
        _qc_or_legacy(base_query, "VIP Pipeline", _legacy_vip_match())
    )
    hot_leads = await db.leads.count_documents(
        {
            **base_query,
            "$or": [
                {"qualification_category": "Hot"},
                {"$and": [_missing_qualification_clause(), _legacy_hot_match()]},
            ],
        }
    )
    cold_leads = await db.leads.count_documents(
        {
            **base_query,
            "$or": [
                {"qualification_category": "Cold"},
                {"$and": [_missing_qualification_clause(), _legacy_cold_match()]},
            ],
        }
    )
    dormant_leads = await db.leads.count_documents(_dormant_bucket_query(base_query))

    warm_leads = await db.leads.count_documents(
        merge(
            {
                "$or": [
                    {"temperature": "Warm"},
                    {"status": "Warm Lead"},
                ]
            }
        )
    )
    interested_leads = await db.leads.count_documents(
        merge({"ai_disposition": {"$in": list(_AI_INTERESTED)}})
    )
    lost_leads = await db.leads.count_documents(merge({"status": "Lost"}))
    site_visits_scheduled = await db.leads.count_documents(merge({"status": "Site Visit Scheduled"}))

    async def get_distribution(field: str):
        pipeline = [
            {"$match": base_query},
            {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
        ]
        results = await db.leads.aggregate(pipeline).to_list(length=100)
        return {str(r["_id"]) if r["_id"] else "Other": r["count"] for r in results}

    lead_status_stats = await get_distribution("status")
    lead_source_stats = await get_distribution("source")
    regional_demand = await get_distribution("location_category")
    budget_distribution = await get_distribution("budget_category")

    disposition_pipeline = [
        {"$match": base_query},
        {
            "$project": {
                "disp": {
                    "$cond": [
                        {
                            "$and": [
                                {"$ne": ["$disposition", None]},
                                {"$ne": ["$disposition", ""]},
                                {"$ne": ["$disposition", "New"]},
                            ]
                        },
                        "$disposition",
                        {
                            "$cond": [
                                {
                                    "$and": [
                                        {"$ne": ["$ai_disposition", None]},
                                        {"$ne": ["$ai_disposition", ""]},
                                    ]
                                },
                                "$ai_disposition",
                                "Other",
                            ]
                        },
                    ]
                }
            }
        },
        {"$group": {"_id": "$disp", "count": {"$sum": 1}}},
    ]
    disp_rows = await db.leads.aggregate(disposition_pipeline).to_list(50)
    disposition_stats = {
        str(r["_id"]) if r["_id"] else "Other": r["count"] for r in disp_rows
    }

    return {
        "total_leads": total_leads,
        "hot_leads": hot_leads,
        "warm_leads": warm_leads,
        "cold_leads": cold_leads,
        "interested_leads": interested_leads,
        "site_visits_scheduled": site_visits_scheduled,
        "lost_leads": lost_leads,
        "dormant_leads": dormant_leads,
        "vip_pipeline": vip_pipeline,
        "qualified_leads": qualified_leads,
        "lead_status_stats": lead_status_stats,
        "lead_source_stats": lead_source_stats,
        "regional_demand": regional_demand,
        "budget_distribution": budget_distribution,
        "disposition_stats": disposition_stats,
    }


def _date_filter_query(
    project: Optional[str],
    days: Optional[int],
    start_date: Optional[str],
    end_date: Optional[str],
) -> Dict[str, Any]:
    base_query: Dict[str, Any] = {}
    if project and project != "all":
        base_query["project"] = project
    if days:
        cutoff = datetime.utcnow() - timedelta(days=days)
        base_query["created_at"] = {"$gte": cutoff}
    elif start_date or end_date:
        date_filter: Dict[str, Any] = {}
        if start_date:
            try:
                date_filter["$gte"] = datetime.strptime(start_date, "%Y-%m-%d")
            except ValueError:
                pass
        if end_date:
            try:
                date_filter["$lte"] = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            except ValueError:
                pass
        if date_filter:
            base_query["created_at"] = date_filter
    return base_query


@router.get("/sales-owners")
async def get_sales_owners(
    project: Optional[str] = None,
    days: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db=Depends(get_db),
):
    """Top 10 presales agents by assigned lead count (same rep logic as Sales Dashboard)."""
    base_query = _date_filter_query(project, days, start_date, end_date)
    rep_expr = _rep_name_expression()
    pipeline = [
        {"$match": base_query},
        {"$addFields": {"rep": rep_expr}},
        {"$match": {"rep": {"$nin": ["Unassigned", None, ""]}}},
        {"$group": {"_id": "$rep", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    results = await db.leads.aggregate(pipeline).to_list(length=10)
    out: List[Dict[str, Any]] = []
    for r in results:
        name = str(r["_id"] or "").strip()
        if not name or _is_invalid_rep_name(name):
            continue
        out.append({"name": name, "count": int(r.get("count", 0))})
    return out


@router.get("/projects")
async def get_top_projects(db=Depends(get_db)):
    total_leads = await db.leads.count_documents({})
    with_project = await db.leads.count_documents(_merge_query_with_valid_projects({}))

    pipeline = [
        {"$match": _merge_query_with_valid_projects({})},
        {"$group": {"_id": "$project", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
        {"$project": {"name": "$_id", "count": 1, "_id": 0}},
    ]
    raw = await db.leads.aggregate(pipeline).to_list(length=10)
    projects = [
        p
        for p in raw
        if p.get("name") and p.get("name") != "Profiling in Progress"
    ]
    top_sum = sum(int(p.get("count", 0)) for p in projects)
    other_count = max(0, with_project - top_sum)

    return {
        "projects": projects,
        "total_leads": total_leads,
        "with_project": with_project,
        "other_count": other_count,
        "without_project": max(0, total_leads - with_project),
    }
