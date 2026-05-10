import uvicorn
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.core.config import settings
from app.core.database import connect_to_mongo, close_mongo_connection, initialize_db, get_db
from app.api.v1 import leads, dashboard, ai, webhooks, campaigns, projects, agents

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.PROJECT_NAME)

# CORS — allow all origins in development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_db_client():
    await connect_to_mongo()
    await initialize_db()
    logger.info("✅ Backend started — Rustomjee Sales Intelligence API")

@app.on_event("shutdown")
async def shutdown_db_client():
    await close_mongo_connection()

@app.get("/")
async def root():
    return {"status": "ok", "service": "rustomjee-sales-api"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# ── API Routers ──────────────────────────────────────────────────────────────
app.include_router(leads.router,      prefix="/api/leads",      tags=["Leads"])
app.include_router(dashboard.router,  prefix="/api/dashboard",  tags=["Dashboard"])
app.include_router(ai.router,         prefix="/api",            tags=["AI"])
app.include_router(webhooks.router,   prefix="/api/webhooks",   tags=["Webhooks"])
app.include_router(campaigns.router,  prefix="/api/campaigns",  tags=["Campaigns"])
app.include_router(projects.router,   prefix="/api/projects",   tags=["Projects"])
app.include_router(agents.router,     prefix="/api/agents",     tags=["Agents"])

# ── Call History endpoint ─────────────────────────────────────────────────────
@app.get("/api/call-history")
async def get_call_history(
    campaign: str = None,
    status: str = None,
    disposition: str = None,
    limit: int = 0,
    offset: int = 0,
    db = Depends(get_db)
):
    """
    Returns merged call history from both:
    1. call_history collection (from Futwork webhooks)
    2. leads collection (legacy embedded call data)
    """
    try:
        calls = []
        campaigns_set = set()

        # ── 1. call_history collection (from Futwork webhooks) ─────────────
        ch_query = {}
        if campaign and campaign != "all":
            ch_query["campaign"] = campaign
        if disposition and disposition != "all":
            ch_query["disposition"] = disposition
        if status and status != "all":
            ch_query["status"] = status

        fetch_cap = limit if limit > 0 else 100000
        ch_cursor = db.call_history.find(ch_query, {"_id": 0}).sort("created_at", -1)
        if offset:
            ch_cursor = ch_cursor.skip(offset)
        ch_docs = await ch_cursor.to_list(fetch_cap)

        for doc in ch_docs:
            campaign_name = doc.get("campaign", "") or "Default Campaign"
            campaigns_set.add(campaign_name)
            calls.append({
                "id": doc.get("id", doc.get("call_sid", "")),
                "customer_name": doc.get("customer_name", "Unknown"),
                "phone": doc.get("phone", ""),
                "status": doc.get("status", ""),
                "disposition": doc.get("disposition", ""),
                "duration": int(doc.get("duration", 0) or 0),
                "recording_url": doc.get("recording_url", ""),
                "transcript": doc.get("transcript", ""),
                "created_at": doc.get("started_at", doc.get("created_at", "")),
                "campaign": campaign_name,
                "lead_id": doc.get("lead_id", ""),
                "direction": "outbound",
                "hangup_by": "bot",
            })

        # ── 2. leads collection (legacy embedded call data) ──────────────
        # Only fall back to leads if call_history is empty (avoids duplicates)
        if not calls:
            base_query = {
                "$or": [
                    {"call_status": {"$nin": ["", None]}},
                    {"recording_url": {"$nin": ["", None]}},
                ]
            }
            if campaign and campaign != "all":
                base_query["campaign_name"] = campaign
            if disposition and disposition != "all":
                base_query["disposition"] = disposition
            if status and status != "all":
                base_query["$and"] = [{
                    "$or": [
                        {"call_status": {"$regex": f"^{status}$", "$options": "i"}},
                    ]
                }]

            leads_cursor = db.leads.find(base_query, {"_id": 0}).sort("created_at", -1)
            if offset:
                leads_cursor = leads_cursor.skip(offset)
            leads_data = await leads_cursor.to_list(fetch_cap)

            for lead in leads_data:
                call_status = lead.get("call_status", "") or "completed"
                campaign_name = lead.get("campaign_name", "") or "Default Campaign"
                campaigns_set.add(campaign_name)
                calls.append({
                    "id": lead.get("id", ""),
                    "customer_name": lead.get("full_name", "Unknown"),
                    "phone": lead.get("mobile", ""),
                    "status": call_status,
                    "disposition": lead.get("disposition", ""),
                    "duration": int(lead.get("call_duration", 0) or 0),
                    "recording_url": lead.get("recording_url", ""),
                    "transcript": lead.get("transcript", ""),
                    "created_at": lead.get("call_date", lead.get("created_at", "")),
                    "campaign": campaign_name,
                    "lead_id": lead.get("id", ""),
                    "direction": "outbound",
                    "hangup_by": "bot",
                })

        # ── Campaigns list for filter dropdown ────────────────────────────
        all_campaign_names = await db.campaigns.distinct("name")
        ch_campaign_names = await db.call_history.distinct("campaign")
        lead_campaign_names = await db.leads.distinct("campaign_name")

        all_campaigns_merged = sorted(set(
            [c for c in (all_campaign_names + ch_campaign_names + lead_campaign_names) if c]
        ))

        return {
            "calls": calls,
            "campaigns": all_campaigns_merged or sorted(campaigns_set),
            "total": len(calls)
        }
    except Exception as e:
        logger.error(f"Error fetching call history: {e}")
        return {"calls": [], "campaigns": [], "total": 0}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
