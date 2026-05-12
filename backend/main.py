import re
import uvicorn
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.core.config import settings
from app.core.database import connect_to_mongo, close_mongo_connection, initialize_db, get_db
from app.api.v1 import leads, dashboard, ai, webhooks, campaigns, projects, agents
from app.models.structured_extraction import StructuredDisposition

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
app.include_router(leads.router, prefix="/api/leads", tags=["Leads"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(ai.router, prefix="/api", tags=["AI"])
app.include_router(webhooks.router, prefix="/api/webhooks", tags=["Webhooks"])
app.include_router(campaigns.router, prefix="/api/campaigns", tags=["Campaigns"])
app.include_router(projects.router, prefix="/api/projects", tags=["Projects"])
app.include_router(agents.router, prefix="/api/agents", tags=["Agents"])


def _and_queries(*parts: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = [p for p in parts if p]
    if not merged:
        return {}
    if len(merged) == 1:
        return merged[0]
    return {"$and": merged}


def _call_history_filter_query(
    campaign: Optional[str],
    status: Optional[str],
    disposition: Optional[str],
    search: Optional[str],
) -> Dict[str, Any]:
    parts: List[Dict[str, Any]] = []
    if campaign and campaign != "all":
        parts.append({"campaign": campaign})
    if disposition and disposition != "all":
        parts.append({"disposition": disposition})
    if status and status != "all":
        parts.append({"status": status})

    q = (search or "").strip()
    if q:
        esc = re.escape(q)
        digits = re.sub(r"\D+", "", q)
        or_clauses: List[Dict[str, Any]] = [
            {"customer_name": {"$regex": esc, "$options": "i"}},
            {"phone": {"$regex": esc, "$options": "i"}},
        ]
        if digits:
            or_clauses.append({"mobile_digits": {"$regex": digits}})
            if len(digits) > 10:
                or_clauses.append({"mobile_digits": {"$regex": digits[-10:]}})
        parts.append({"$or": or_clauses})

    return _and_queries(*parts)


def _doc_to_call_row(doc: Dict[str, Any]) -> Dict[str, Any]:
    campaign_name = doc.get("campaign", "") or "Default Campaign"
    return {
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
    }


@app.get("/api/call-history/filters")
async def get_call_history_filters(db=Depends(get_db)):
    """Distinct filter values — small payload for dropdowns."""
    try:
        all_campaign_names = await db.campaigns.distinct("name")
        ch_campaign_names = await db.call_history.distinct("campaign")
        lead_campaign_names = await db.leads.distinct("campaign_name")
        campaigns_merged = sorted(
            set(
                c
                for c in (all_campaign_names + ch_campaign_names + lead_campaign_names)
                if c
            )
        )

        statuses = sorted(
            {s for s in await db.call_history.distinct("status") if s is not None and str(s).strip()}
        )
        dispositions = sorted(
            {
                d
                for d in await db.call_history.distinct("disposition")
                if d is not None and str(d).strip()
            }
        )

        return {
            "campaigns": campaigns_merged,
            "statuses": statuses,
            "dispositions": dispositions,
        }
    except Exception as e:
        logger.error("Error fetching call history filters: %s", e)
        return {"campaigns": [], "statuses": [], "dispositions": []}


@app.get("/api/call-history/summary")
async def get_call_history_summary(
    campaign: str = None,
    status: str = None,
    disposition: str = None,
    q: str = None,
    db=Depends(get_db),
):
    """Aggregated KPIs for call_history matching the same filters as the list endpoint."""
    try:
        base = _call_history_filter_query(campaign, status, disposition, q)
        total = await db.call_history.count_documents(base)

        completed_q = _and_queries(
            base,
            {"status": {"$regex": r"^completed$", "$options": "i"}},
        )
        interested_q = _and_queries(
            base,
            {
                "structured_extraction.disposition": {
                    "$in": ["Hot Lead", "Mildly interested"],
                }
            },
        )
        semi_q = _and_queries(
            base,
            {"structured_extraction.disposition": {"$in": ["Semi-Interested", "Semi-interested"]}},
        )
        interested_fallback = _and_queries(
            base,
            {"disposition": {"$regex": r"^interested$", "$options": "i"}},
        )
        semi_fallback = _and_queries(
            base,
            {"disposition": {"$regex": r"^semi[\s-]*interested$", "$options": "i"}},
        )

        completed = await db.call_history.count_documents(completed_q)
        interested = await db.call_history.count_documents(interested_q)
        semi_interested = await db.call_history.count_documents(semi_q)
        if interested == 0:
            interested = await db.call_history.count_documents(interested_fallback)
        if semi_interested == 0:
            semi_interested = await db.call_history.count_documents(semi_fallback)

        pipeline = [{"$match": base}, {"$group": {"_id": None, "avg": {"$avg": "$duration"}}}]
        agg = await db.call_history.aggregate(pipeline).to_list(1)
        avg_duration = 0.0
        if agg and agg[0].get("avg") is not None:
            avg_duration = float(agg[0]["avg"])

        return {
            "total_calls": total,
            "completed": completed,
            "interested": interested,
            "semi_interested": semi_interested,
            "avg_duration_seconds": round(avg_duration) if total else 0,
        }
    except Exception as e:
        logger.error("Error in call history summary: %s", e)
        return {
            "total_calls": 0,
            "completed": 0,
            "interested": 0,
            "semi_interested": 0,
            "avg_duration_seconds": 0,
        }


@app.get("/api/call-history/ai-batch-summary")
async def get_call_history_ai_batch_summary(
    campaign: str = None,
    status: str = None,
    disposition: str = None,
    q: str = None,
    db=Depends(get_db),
):
    """
    Batch summary computed from AI structured extractions stored on call_history.
    Returns a shape compatible with the frontend \"Batch Summary\" view.
    """
    try:
        base = _call_history_filter_query(campaign, status, disposition, q)
        # Only consider calls with structured extraction present
        base = _and_queries(base, {"structured_extraction.disposition": {"$exists": True, "$ne": ""}})

        total = await db.call_history.count_documents(base)
        if total == 0:
            return {
                "batch_summary": {
                    "total_calls": 0,
                    "hot_leads": 0,
                    "semi_interested": 0,
                    "mildly_interested": 0,
                    "not_interested": 0,
                    "voicemail_wrong_number": 0,
                    "already_bought": 0,
                    "system_tags_incorrect": 0,
                    "top_priority_leads": [],
                    "crm_issues_detected": [],
                }
            }

        # Aggregate counts by AI disposition
        pipeline = [
            {"$match": base},
            {"$group": {"_id": "$structured_extraction.disposition", "count": {"$sum": 1}}},
        ]
        rows = await db.call_history.aggregate(pipeline).to_list(length=50)
        counts = {str(r["_id"]): int(r["count"]) for r in rows if r.get("_id")}

        system_incorrect = await db.call_history.count_documents(
            _and_queries(base, {"structured_extraction.system_tag_correct": False})
        )

        # Priority leads: choose Hot, then Semi, then Mild by recency
        pri_disp = [
            StructuredDisposition.hot_lead.value,
            StructuredDisposition.semi_interested.value,
            "Semi-interested",
            StructuredDisposition.mildly_interested.value,
        ]
        pri_cursor = (
            db.call_history.find(
                _and_queries(base, {"structured_extraction.disposition": {"$in": pri_disp}}),
                {"_id": 0, "structured_extraction.lead_name": 1, "structured_extraction.phone": 1, "created_at": 1},
            )
            .sort("created_at", -1)
            .limit(50)
        )
        pri_docs = await pri_cursor.to_list(50)
        top_priority = []
        seen = set()
        for d in pri_docs:
            se = d.get("structured_extraction") or {}
            name = (se.get("lead_name") or "Unknown").strip() or "Unknown"
            phone = (se.get("phone") or "").strip()
            key = f"{name}|{phone}"
            if key in seen:
                continue
            seen.add(key)
            top_priority.append(f"{name} ({phone})" if phone else name)
            if len(top_priority) >= 3:
                break

        return {
            "batch_summary": {
                "total_calls": total,
                "hot_leads": int(counts.get(StructuredDisposition.hot_lead.value, 0)),
                "semi_interested": int(
                    counts.get(StructuredDisposition.semi_interested.value, 0)
                    + counts.get("Semi-interested", 0)
                ),
                "mildly_interested": int(counts.get(StructuredDisposition.mildly_interested.value, 0)),
                "not_interested": int(counts.get(StructuredDisposition.not_interested.value, 0)),
                "voicemail_wrong_number": int(counts.get(StructuredDisposition.voicemail.value, 0))
                + int(counts.get(StructuredDisposition.wrong_number.value, 0)),
                "already_bought": int(counts.get(StructuredDisposition.already_bought.value, 0)),
                "system_tags_incorrect": int(system_incorrect),
                "top_priority_leads": top_priority,
                "crm_issues_detected": [],
            }
        }
    except Exception as e:
        logger.error("Error in ai batch summary: %s", e)
        return {
            "batch_summary": {
                "total_calls": 0,
                "hot_leads": 0,
                "semi_interested": 0,
                "mildly_interested": 0,
                "not_interested": 0,
                "voicemail_wrong_number": 0,
                "already_bought": 0,
                "system_tags_incorrect": 0,
                "top_priority_leads": [],
                "crm_issues_detected": [],
            }
        }


@app.get("/api/call-history")
async def get_call_history(
    campaign: str = None,
    status: str = None,
    disposition: str = None,
    q: str = None,
    page: int = 1,
    size: int = 50,
    limit: int = 0,
    offset: int = 0,
    db=Depends(get_db),
):
    """
    Paginated call history from call_history (webhooks), with legacy leads fallback
    only when call_history is empty for this deployment.
    """
    try:
        ch_query = _call_history_filter_query(campaign, status, disposition, q)

        # Legacy: offset/limit when page not used explicitly (limit>0 and page is default)
        use_legacy_pagination = limit > 0 and page == 1 and size == 50
        if use_legacy_pagination:
            skip_n = offset
            limit_n = limit if limit > 0 else 100000
        else:
            page = max(1, page)
            size = min(max(1, size), 500)
            skip_n = (page - 1) * size
            limit_n = size

        calls: List[Dict[str, Any]] = []
        total = 0
        has_more = False
        effective_page = page if not use_legacy_pagination else 1
        effective_size = limit_n if use_legacy_pagination else size

        call_history_collection_used = await db.call_history.count_documents({}) > 0

        if call_history_collection_used:
            total = await db.call_history.count_documents(ch_query)
            ch_cursor = (
                db.call_history.find(ch_query, {"_id": 0})
                .sort("created_at", -1)
                .skip(skip_n)
                .limit(limit_n)
            )
            ch_docs = await ch_cursor.to_list(limit_n)
            has_more = skip_n + len(ch_docs) < total

            for doc in ch_docs:
                calls.append(_doc_to_call_row(doc))
        else:
            # Legacy embedded call data on leads — only when call_history collection is empty
            legacy_parts: List[Dict[str, Any]] = [
                {
                    "$or": [
                        {"call_status": {"$nin": ["", None]}},
                        {"recording_url": {"$nin": ["", None]}},
                    ]
                }
            ]
            if campaign and campaign != "all":
                legacy_parts.append({"campaign_name": campaign})
            if disposition and disposition != "all":
                legacy_parts.append({"disposition": disposition})
            if status and status != "all":
                legacy_parts.append(
                    {"$or": [{"call_status": {"$regex": f"^{status}$", "$options": "i"}}]}
                )

            sq = (q or "").strip()
            if sq:
                esc = re.escape(sq)
                digits = re.sub(r"\D+", "", sq)
                ors = [
                    {"full_name": {"$regex": esc, "$options": "i"}},
                    {"mobile": {"$regex": esc, "$options": "i"}},
                ]
                if digits:
                    ors.append({"mobile_digits": {"$regex": digits}})
                legacy_parts.append({"$or": ors})

            base_query = _and_queries(*legacy_parts)

            total = await db.leads.count_documents(base_query)
            leads_cursor = (
                db.leads.find(base_query, {"_id": 0})
                .sort("created_at", -1)
                .skip(skip_n)
                .limit(limit_n)
            )
            leads_data = await leads_cursor.to_list(limit_n)
            has_more = skip_n + len(leads_data) < total

            for lead in leads_data:
                call_status = lead.get("call_status", "") or "completed"
                campaign_name = lead.get("campaign_name", "") or "Default Campaign"
                calls.append(
                    {
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
                    }
                )

        return {
            "calls": calls,
            "total": total,
            "page": effective_page,
            "size": effective_size,
            "has_more": has_more,
        }
    except Exception as e:
        logger.error(f"Error fetching call history: {e}")
        return {
            "calls": [],
            "total": 0,
            "page": 1,
            "size": size,
            "has_more": False,
        }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
