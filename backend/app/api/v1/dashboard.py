from fastapi import APIRouter, Depends, Query
from typing import Optional
from datetime import datetime, timedelta
from ...core.database import get_db
from ...models.stats import DashboardStats

router = APIRouter()

@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    project: Optional[str] = None,
    days: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db = Depends(get_db)
):
    # Build base time/project filter
    base_query = {}
    if project and project != "all":
        base_query["project"] = project

    if days:
        cutoff = datetime.utcnow() - timedelta(days=days)
        base_query["created_at"] = {"$gte": cutoff}
    elif start_date or end_date:
        date_filter = {}
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

    # Total counts
    total_leads = await db.leads.count_documents(base_query)
    hot_leads = await db.leads.count_documents(merge({"temperature": "Hot"}))
    warm_leads = await db.leads.count_documents(merge({"temperature": "Warm"}))
    cold_leads = await db.leads.count_documents(merge({"temperature": "Cold"}))
    interested_leads = await db.leads.count_documents(merge({"disposition": "Interested"}))
    lost_leads = await db.leads.count_documents(merge({"status": "Lost"}))
    site_visits_scheduled = await db.leads.count_documents(merge({"status": "Site Visit Scheduled"}))

    # VIP Pipeline (hot leads + HNI/5Cr+)
    vip_pipeline = await db.leads.count_documents(merge({"is_vip": True}))

    # Qualified Leads
    qualified_leads = await db.leads.count_documents(merge({"status": "Qualified"}))

    # Dormant = not contacted in 30+ days or Lost
    dormant_leads = await db.leads.count_documents(merge({
        "$or": [
            {"status": "Lost"},
            {"temperature": "Cold"}
        ]
    }))

    # Aggregations
    async def get_distribution(field: str):
        pipeline = [
            {"$match": base_query},
            {"$group": {"_id": f"${field}", "count": {"$sum": 1}}}
        ]
        results = await db.leads.aggregate(pipeline).to_list(length=100)
        return {str(r["_id"]) if r["_id"] else "Other": r["count"] for r in results}

    lead_status_stats = await get_distribution("status")
    lead_source_stats = await get_distribution("source")
    regional_demand = await get_distribution("location_category")
    budget_distribution = await get_distribution("budget_category")

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
        "budget_distribution": budget_distribution
    }

@router.get("/projects")
async def get_top_projects(db = Depends(get_db)):
    pipeline = [
        {"$group": {"_id": "$project", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
        {"$project": {"name": "$_id", "count": 1, "_id": 0}}
    ]
    return await db.leads.aggregate(pipeline).to_list(length=10)
