"""
DB Diagnostic Script -- Rustomjee CRM
Checks the actual state of leads and call_history in MongoDB.
Run from backend/ directory:
    python scripts/db_diagnostic.py
"""
import asyncio
import os
import sys
from dotenv import load_dotenv

# Load .env from the backend directory
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.getenv("MONGO_URL", "")
DB_NAME   = os.getenv("DB_NAME", "rustomjee_db")


async def run():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    print("=" * 65)
    print("  RUSTOMJEE CRM -- DB DIAGNOSTIC REPORT")
    print("=" * 65)

    # -- 1. Total leads -----------------------------------------------
    total_leads = await db.leads.count_documents({})
    print(f"\n[LEADS COLLECTION]  Total documents: {total_leads}")

    # -- 2. futwork_sync_status breakdown -----------------------------
    print("\n  futwork_sync_status breakdown:")
    statuses = ["pending", "pushed", "failed", None]
    for s in statuses:
        if s is None:
            q = {"$or": [{"futwork_sync_status": {"$exists": False}}, {"futwork_sync_status": None}]}
            label = "null/missing"
        else:
            q = {"futwork_sync_status": s}
            label = s
        count = await db.leads.count_documents(q)
        print(f"    {label:<20} : {count}")

    # -- 3. Eligible for push (the number shown in UI) ----------------
    eligible_q = {
        "client_lead_id": {"$exists": True, "$nin": ["", None]},
        "mobile_digits": {"$regex": r"^\d{10}$"},
        "$or": [
            {"futwork_sync_status": {"$in": ["pending", "failed"]}},
            {"futwork_sync_status": {"$exists": False}},
            {"futwork_sync_status": None},
        ],
    }
    eligible_count = await db.leads.count_documents(eligible_q)
    print(f"\n  [!!] Eligible for push (shown in UI): {eligible_count}")

    # -- 4. Already called but still pending --------------------------
    already_called_pending = await db.leads.count_documents({
        "futwork_sync_status": {"$in": ["pending", "failed"]},
        "last_call_status": {"$exists": True, "$nin": ["", None]},
    })
    print(f"\n  [BAD] Already called but still 'pending'/'failed': {already_called_pending}")
    print("        These are showing up wrongly in the push queue")

    # -- 5. Leads matched to a call_history record --------------------
    pending_leads = await db.leads.find(
        {"futwork_sync_status": {"$in": ["pending", "failed"]},
         "client_lead_id": {"$exists": True, "$nin": ["", None]}},
        {"_id": 0, "id": 1, "mobile_digits": 1, "client_lead_id": 1}
    ).to_list(length=50000)

    print(f"\n  Checking {len(pending_leads)} pending leads against call_history...")

    mobile_set = set(
        l["mobile_digits"] for l in pending_leads
        if (l.get("mobile_digits") or "").strip()
    )
    client_id_set = set(
        l["client_lead_id"] for l in pending_leads
        if (l.get("client_lead_id") or "").strip()
    )

    # Count how many have calls in call_history by mobile
    calls_by_mobile = await db.call_history.count_documents({
        "mobile_digits": {"$in": list(mobile_set)}
    }) if mobile_set else 0

    calls_by_client_id = await db.call_history.count_documents({
        "client_lead_id": {"$in": list(client_id_set)}
    }) if client_id_set else 0

    print(f"  call_history rows matching pending leads by mobile      : {calls_by_mobile}")
    print(f"  call_history rows matching pending leads by client_id   : {calls_by_client_id}")

    # -- 6. Leads with NO client_lead_id (orphans) --------------------
    no_client_id = await db.leads.count_documents({
        "$or": [
            {"client_lead_id": {"$exists": False}},
            {"client_lead_id": None},
            {"client_lead_id": ""},
        ]
    })
    print(f"\n  Leads with NO client_lead_id (orphan/direct webhook)   : {no_client_id}")

    orphan_source = await db.leads.count_documents({"source": "futwork_orphan_call"})
    print(f"  Leads with source='futwork_orphan_call'                 : {orphan_source}")

    fw_call_prefix = await db.leads.count_documents(
        {"client_lead_id": {"$regex": r"^FW-CALL-"}}
    )
    print(f"  Leads with auto-generated FW-CALL-* client_lead_id     : {fw_call_prefix}")

    # -- 7. call_history overview -------------------------------------
    total_calls = await db.call_history.count_documents({})
    calls_no_lead = await db.call_history.count_documents({
        "$or": [{"lead_id": {"$exists": False}}, {"lead_id": None}, {"lead_id": ""}]
    })
    calls_with_lead = total_calls - calls_no_lead

    terminal_statuses = ["completed", "no-answer", "busy", "failed", "call-disconnected"]
    terminal_calls = await db.call_history.count_documents({
        "status": {"$in": terminal_statuses}
    })

    print(f"\n[CALL_HISTORY COLLECTION]  Total documents: {total_calls}")
    print(f"  With lead_id linked      : {calls_with_lead}")
    print(f"  With NO lead_id (orphan) : {calls_no_lead}")
    print(f"  Terminal status calls    : {terminal_calls}")

    # -- 8. Distinct campaign_ids in call_history ---------------------
    campaign_ids = await db.call_history.distinct("campaign_id")
    campaign_ids = [c for c in campaign_ids if c]
    print(f"\n  Distinct campaign_ids in call_history: {len(campaign_ids)}")
    for cid in campaign_ids:
        cnt = await db.call_history.count_documents({"campaign_id": cid})
        print(f"    {cid} --> {cnt} calls")

    # -- 9. disposition breakdown in leads ----------------------------
    print(f"\n[LEADS] disposition breakdown (top 10):")
    pipeline = [
        {"$group": {"_id": "$disposition", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    rows = await db.leads.aggregate(pipeline).to_list(10)
    for r in rows:
        print(f"    {str(r['_id'] or 'null/empty'):<35} : {r['count']}")

    # -- 10. last_call_status breakdown on leads ----------------------
    print(f"\n[LEADS] last_call_status breakdown:")
    pipeline2 = [
        {"$group": {"_id": "$last_call_status", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    rows2 = await db.leads.aggregate(pipeline2).to_list(20)
    for r in rows2:
        print(f"    {str(r['_id'] or 'null/empty'):<35} : {r['count']}")

    # -- 11. How many should be marked pushed -------------------------
    should_be_pushed = await db.leads.count_documents({
        "futwork_sync_status": {"$in": ["pending", "failed", None]},
        "last_call_status": {"$in": ["completed", "no-answer", "busy", "failed",
                                     "call-disconnected", "no_answer"]},
        "client_lead_id": {"$exists": True, "$nin": ["", None]},
    })
    print(f"\n  [FIX] Leads to backfill (pending + already called): {should_be_pushed}")
    print("        Run the fix script to mark these as 'pushed'.")

    # -- 12. Leads with last_call_date but still pending --------------
    has_call_date_pending = await db.leads.count_documents({
        "futwork_sync_status": {"$in": ["pending", None]},
        "last_call_date": {"$exists": True, "$ne": None},
    })
    print(f"  [FIX] Pending leads with last_call_date set             : {has_call_date_pending}")

    # -- 13. Source breakdown on ALL leads ----------------------------
    print(f"\n[LEADS] source breakdown:")
    pipeline3 = [
        {"$group": {"_id": "$source", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    rows3 = await db.leads.aggregate(pipeline3).to_list(20)
    for r in rows3:
        print(f"    {str(r['_id'] or 'null/empty'):<35} : {r['count']}")

    print("\n" + "=" * 65)
    print("  DIAGNOSTIC COMPLETE")
    print("=" * 65)

    client.close()


if __name__ == "__main__":
    asyncio.run(run())
