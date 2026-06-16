from fastapi import APIRouter, Depends, Query
from typing import Optional, Any, Dict, List
from ...core.database import get_db
from ...models.stats import DashboardStats
from ...services.qualification_buckets import (
    _AI_INTERESTED,
    build_base_query,
    bucket_query,
)
from ...utils.futwork_disposition_stats import (
    aggregate_futwork_disposition_stats,
    aggregate_avg_duration_by_disposition,
    build_call_history_match_query,
    resolve_project_call_correlation,
    futwork_disposition_exact,
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
    # total_leads is now computed from call_history distinct numbers below
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

    lead_status_stats = {
        "Cold": cold_leads,
        "Dormant": dormant_leads,
        "Warm": warm_leads,
        "Hot": hot_leads,
        "Qualified": qualified_leads,
    }
    lead_source_stats = await get_distribution("source")
    regional_demand = await get_distribution("location_category")
    budget_distribution = await get_distribution("budget_category")

    # Futwork call-level dispositions (same source as AI Calling KPIs).
    disposition_stats = await aggregate_futwork_disposition_stats(
        db,
        project=project,
        days=days,
        start_date=start_date,
        end_date=end_date,
    )
    
    disposition_avg_duration = await aggregate_avg_duration_by_disposition(
        db,
        project=project,
        days=days,
        start_date=start_date,
        end_date=end_date,
    )

    lead_ids, mobile_digits_list = [], []
    if project and project != "all":
        lead_ids, mobile_digits_list = await resolve_project_call_correlation(db, project)

    ch_query = build_call_history_match_query(
        project=project,
        days=days,
        start_date=start_date,
        end_date=end_date,
        lead_ids=lead_ids or None,
        mobile_digits_list=mobile_digits_list or None,
    )
    
    total_calls = await db.call_history.count_documents(ch_query)
    
    total_leads_list = await db.call_history.distinct("mobile_digits", ch_query)
    total_leads = len(total_leads_list)
    
    pipeline = [
        {"$match": {**ch_query, "duration": {"$gt": 0}}},
        {"$group": {
            "_id": None, 
            "total_duration": {"$sum": "$duration"}, 
            "avg_duration": {"$avg": "$duration"},
            "total_billed": {"$sum": {"$ceil": {"$divide": ["$duration", 60]}}}
        }}
    ]
    ch_agg = await db.call_history.aggregate(pipeline).to_list(1)
    
    total_duration_seconds = 0
    avg_call_duration = 0
    total_billed_minutes = 0
    if ch_agg:
        total_duration_seconds = ch_agg[0].get("total_duration") or 0
        avg_call_duration = round(ch_agg[0].get("avg_duration") or 0)
        total_billed_minutes = int(ch_agg[0].get("total_billed") or 0)
    
    site_visit_query = {**ch_query, **futwork_disposition_exact("Site Visit")}
    site_visits = await db.call_history.count_documents(site_visit_query)
    
    interested_query = {**ch_query, **futwork_disposition_exact("Interested")}
    interested_calls = await db.call_history.count_documents(interested_query)

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
        "total_calls": total_calls,
        "total_billed_minutes": total_billed_minutes,
        "avg_call_duration": avg_call_duration,
        "site_visits": site_visits,
        "interested_calls": interested_calls,
        "lead_status_stats": lead_status_stats,
        "lead_source_stats": lead_source_stats,
        "regional_demand": regional_demand,
        "budget_distribution": budget_distribution,
        "disposition_stats": disposition_stats,
        "disposition_avg_duration": disposition_avg_duration,
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
