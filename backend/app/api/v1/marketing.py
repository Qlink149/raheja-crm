import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...core.database import get_db
from ...core.security import get_current_user
from ...core.time_utils import iso_utc_now, utc_now

router = APIRouter()

_SEED_SPENDS: List[Dict[str, Any]] = [
    {
        "id": "seed-mkt-google-1",
        "project": "Rustomjee ECR",
        "channel": "google_ads",
        "amount": 85000.0,
        "leads_generated": 42,
        "conversions": 5,
        "period": "2026-Q1",
        "campaign_name": "Google Search - ECR Q1",
        "source": "seed",
    },
    {
        "id": "seed-mkt-meta-1",
        "project": "Rustomjee ECR",
        "channel": "meta_ads",
        "amount": 120000.0,
        "leads_generated": 68,
        "conversions": 8,
        "period": "2026-Q1",
        "campaign_name": "Meta Lead Gen - ECR Q1",
        "source": "seed",
    },
    {
        "id": "seed-mkt-print-1",
        "project": "Rustomjee Bandra",
        "channel": "newspaper",
        "amount": 45000.0,
        "leads_generated": 18,
        "conversions": 2,
        "period": "2026-Q1",
        "campaign_name": "Print - Bandra Launch",
        "source": "seed",
    },
    {
        "id": "seed-mkt-events-1",
        "project": "Rustomjee Bandra",
        "channel": "events",
        "amount": 75000.0,
        "leads_generated": 35,
        "conversions": 6,
        "period": "2026-Q1",
        "campaign_name": "Property Expo 2026",
        "source": "seed",
    },
    {
        "id": "seed-mkt-wati-1",
        "project": "Rustomjee ECR",
        "channel": "wati",
        "amount": 25000.0,
        "leads_generated": 52,
        "conversions": 4,
        "period": "2026-Q1",
        "campaign_name": "WhatsApp Broadcast Q1",
        "source": "seed",
    },
    {
        "id": "seed-mkt-google-2",
        "project": "Rustomjee Bandra",
        "channel": "google_ads",
        "amount": 62000.0,
        "leads_generated": 28,
        "conversions": 3,
        "period": "2026-02",
        "campaign_name": "Google Display - Bandra",
        "source": "seed",
    },
]


class MarketingSpendEntry(BaseModel):
    project: str
    channel: str
    amount: float
    leads_generated: int = 0
    conversions: int = 0
    period: str
    campaign_name: Optional[str] = None
    impressions: Optional[int] = None
    clicks: Optional[int] = None
    notes: Optional[str] = None


async def _ensure_seed_spends(db) -> None:
    if await db.marketing_spends.count_documents({}) > 0:
        return
    now_dt = utc_now()
    now_iso = iso_utc_now()
    for row in _SEED_SPENDS:
        doc = dict(row)
        doc["created_at"] = now_iso
        doc["created_at_dt"] = now_dt
        doc["created_by"] = "system"
        doc["created_by_name"] = "System"
        doc["cost_per_lead"] = (
            round(doc["amount"] / doc["leads_generated"], 2) if doc["leads_generated"] > 0 else 0
        )
        doc["cost_per_conversion"] = (
            round(doc["amount"] / doc["conversions"], 2) if doc["conversions"] > 0 else 0
        )
        await db.marketing_spends.update_one({"id": doc["id"]}, {"$set": doc}, upsert=True)


def _aggregate_dashboard(spends: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_project: Dict[str, Any] = {}
    by_channel: Dict[str, Any] = {}
    monthly: Dict[str, Dict[str, float]] = defaultdict(lambda: {"spend": 0.0, "leads": 0.0, "conversions": 0.0})

    for s in spends:
        proj = s.get("project", "Unknown")
        chan = s.get("channel", "Unknown")
        period = s.get("period") or (str(s.get("created_at", ""))[:7] or "Unknown")

        if proj not in by_project:
            by_project[proj] = {
                "project": proj,
                "total_spend": 0,
                "total_leads": 0,
                "total_conversions": 0,
                "channels": {},
            }
        by_project[proj]["total_spend"] += s.get("amount", 0)
        by_project[proj]["total_leads"] += s.get("leads_generated", 0)
        by_project[proj]["total_conversions"] += s.get("conversions", 0)

        if chan not in by_project[proj]["channels"]:
            by_project[proj]["channels"][chan] = {"spend": 0, "leads": 0, "conversions": 0}
        by_project[proj]["channels"][chan]["spend"] += s.get("amount", 0)
        by_project[proj]["channels"][chan]["leads"] += s.get("leads_generated", 0)
        by_project[proj]["channels"][chan]["conversions"] += s.get("conversions", 0)

        if chan not in by_channel:
            by_channel[chan] = {
                "channel": chan,
                "total_spend": 0,
                "total_leads": 0,
                "total_conversions": 0,
            }
        by_channel[chan]["total_spend"] += s.get("amount", 0)
        by_channel[chan]["total_leads"] += s.get("leads_generated", 0)
        by_channel[chan]["total_conversions"] += s.get("conversions", 0)

        monthly[period]["spend"] += s.get("amount", 0)
        monthly[period]["leads"] += s.get("leads_generated", 0)
        monthly[period]["conversions"] += s.get("conversions", 0)

    for proj_data in by_project.values():
        proj_data["cpl"] = (
            round(proj_data["total_spend"] / proj_data["total_leads"], 2)
            if proj_data["total_leads"] > 0
            else 0
        )
        proj_data["cpc"] = (
            round(proj_data["total_spend"] / proj_data["total_conversions"], 2)
            if proj_data["total_conversions"] > 0
            else 0
        )
    for chan_data in by_channel.values():
        chan_data["cpl"] = (
            round(chan_data["total_spend"] / chan_data["total_leads"], 2)
            if chan_data["total_leads"] > 0
            else 0
        )
        chan_data["cpc"] = (
            round(chan_data["total_spend"] / chan_data["total_conversions"], 2)
            if chan_data["total_conversions"] > 0
            else 0
        )

    total_spend = sum(s.get("amount", 0) for s in spends)
    total_leads = sum(s.get("leads_generated", 0) for s in spends)
    total_conversions = sum(s.get("conversions", 0) for s in spends)
    avg_cost_per_lead = round(total_spend / total_leads, 2) if total_leads > 0 else 0
    roi_percent = round((total_conversions / total_spend) * 100, 2) if total_spend > 0 else 0

    monthly_spend = [
        {
            "period": k,
            "total_spend": round(v["spend"], 2),
            "total_leads": int(v["leads"]),
            "total_conversions": int(v["conversions"]),
        }
        for k, v in sorted(monthly.items())
    ]

    return {
        "by_project": list(by_project.values()),
        "by_channel": list(by_channel.values()),
        "total_spend": total_spend,
        "total_leads": total_leads,
        "total_conversions": total_conversions,
        "avg_cost_per_lead": avg_cost_per_lead,
        "roi_percent": roi_percent,
        "monthly_spend": monthly_spend,
        "entries": spends,
    }


@router.post("/spends")
async def add_marketing_spend(
    entry: MarketingSpendEntry,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    doc = entry.model_dump()
    doc["id"] = str(uuid.uuid4())
    now_dt = utc_now()
    now_iso = iso_utc_now()
    doc["created_by"] = current_user["full_name"]
    doc["created_by_user_id"] = current_user["id"]
    doc["created_by_name"] = current_user["full_name"]
    doc["created_at"] = now_iso
    doc["created_at_dt"] = now_dt
    doc["source"] = "manual"
    doc["cost_per_lead"] = (
        round(doc["amount"] / doc["leads_generated"], 2) if doc["leads_generated"] > 0 else 0
    )
    doc["cost_per_conversion"] = (
        round(doc["amount"] / doc["conversions"], 2) if doc["conversions"] > 0 else 0
    )
    await db.marketing_spends.insert_one(doc)
    return {"message": "Spend entry added", "id": doc["id"]}


@router.get("/spends")
async def get_marketing_spends(
    project: Optional[str] = None,
    period: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    query: Dict[str, Any] = {}
    if project:
        query["project"] = project
    if period:
        query["period"] = period
    return await db.marketing_spends.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.get("/dashboard")
async def get_marketing_dashboard(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    await _ensure_seed_spends(db)
    spends = await db.marketing_spends.find({}, {"_id": 0}).to_list(1000)
    return _aggregate_dashboard(spends)


@router.delete("/spends/{spend_id}")
async def delete_marketing_spend(
    spend_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    await db.marketing_spends.delete_one({"id": spend_id})
    return {"message": "Spend entry deleted"}
