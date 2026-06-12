from fastapi import APIRouter, Depends, Query
from typing import Optional, Any, Dict, List
from ...core.database import get_db
from ...models.stats import DashboardStats
from ...services.qualification_buckets import (
    _AI_INTERESTED,
    build_base_query,
    bucket_query,
)
from .analytics import (
    _is_invalid_rep_name,
    _merge_query_with_valid_projects,
    _rep_name_expression,
)

router = APIRouter()


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    project: Optional[str] = None,
    days: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db=Depends(get_db),
):
    base_query = build_base_query(project, days, start_date, end_date)

    def merge(extra: dict) -> dict:
        return {**base_query, **extra}

    total_leads = await db.leads.count_documents(base_query)

    qualified_leads = await db.leads.count_documents(
        bucket_query(base_query, "qualified")
    )
    hot_leads = await db.leads.count_documents(bucket_query(base_query, "hot"))
    cold_leads = await db.leads.count_documents(bucket_query(base_query, "cold"))
    dormant_leads = await db.leads.count_documents(bucket_query(base_query, "dormant"))
    warm_leads = await db.leads.count_documents(bucket_query(base_query, "warm"))
    interested_leads = await db.leads.count_documents(
        merge({"ai_disposition": {"$in": list(_AI_INTERESTED)}})
    )
    lost_leads = await db.leads.count_documents(merge({"status": "Lost"}))
    site_visits_scheduled = await db.leads.count_documents(
        merge({"status": "Site Visit Scheduled"})
    )

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
        "qualified_leads": qualified_leads,
        "lead_status_stats": lead_status_stats,
        "lead_source_stats": lead_source_stats,
        "regional_demand": regional_demand,
        "budget_distribution": budget_distribution,
        "disposition_stats": disposition_stats,
    }


@router.get("/sales-owners")
async def get_sales_owners(
    project: Optional[str] = None,
    days: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db=Depends(get_db),
):
    """Top 10 presales agents by assigned lead count (same rep logic as Sales Dashboard)."""
    base_query = build_base_query(project, days, start_date, end_date)
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
