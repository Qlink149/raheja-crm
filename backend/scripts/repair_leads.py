"""
repair_leads.py — One-time idempotent backfill for rustomjee_db.leads

Repairs the following fields for ALL leads:
  • budget_category   (was missing for Futwork-sourced leads)
  • location_category (same)
  • intent_category   (same)
  • is_vip / is_hni / vip_category  (depended on budget_category)
  • status            (was never mapped from disposition)

Run from the project root:
    cd backend
    python scripts/repair_leads.py
"""

import asyncio
import os
import sys
from datetime import datetime

# Allow imports from backend/app/...
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME   = os.environ.get("DB_NAME", "rustomjee_db")

# Enrichment helpers from the shared util
from app.utils.csv_processor import (
    get_budget_category,
    get_location_category,
    get_intent_category,
)

# Maps the AI-call disposition string → lead status
DISPOSITION_TO_STATUS = {
    "Interested":              "Qualified",
    "Partially Interested":    "Warm Lead",
    "Not Interested":          "Lost",
    "Dropped":                 "Contacted",
    "Incomplete conversation": "Contacted",
    "Busy":                    "Callback",
    "Callback":                "Callback",
}

BATCH_SIZE = 500


async def repair():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    total = await db.leads.count_documents({})
    print(f"\n{'='*60}")
    print(f"  Repair starting — {total} leads in {DB_NAME}")
    print(f"{'='*60}\n")

    skip    = 0
    ops     = []
    updated = 0
    visited = 0

    while True:
        batch = await db.leads.find(
            {},
            {
                "_id": 1,
                "budget": 1,
                "location": 1,
                "current_residence_location": 1,
                "intent": 1,
                "reason_for_purchase": 1,
                "temperature": 1,
                "disposition": 1,
                "status": 1,
                "budget_category": 1,
                "location_category": 1,
                "intent_category": 1,
                "is_vip": 1,
                "is_hni": 1,
                "vip_category": 1,
                "project": 1,
            },
        ).skip(skip).limit(BATCH_SIZE).to_list(BATCH_SIZE)

        if not batch:
            break

        for lead in batch:
            oid = lead["_id"]
            upd: dict = {}

            # ── Category fields ───────────────────────────────────────────
            bc = get_budget_category(lead.get("budget") or "")
            lc = get_location_category(
                lead.get("location") or lead.get("current_residence_location") or ""
            )
            ic = get_intent_category(
                lead.get("intent") or lead.get("reason_for_purchase") or ""
            )

            # Only write if changed (keeps the update idempotent)
            if lead.get("budget_category") != bc:
                upd["budget_category"] = bc
            if lead.get("location_category") != lc:
                upd["location_category"] = lc
            if lead.get("intent_category") != ic:
                upd["intent_category"] = ic

            # ── VIP / HNI flags ───────────────────────────────────────────
            is_vip  = lead.get("temperature") == "Hot" or bc in ("2-5 Cr", "5 Cr+")
            is_hni  = bc == "5 Cr+"
            vip_cat = "VIP/HNI" if is_vip else ""

            if lead.get("is_vip") != is_vip:
                upd["is_vip"] = is_vip
            if lead.get("is_hni") != is_hni:
                upd["is_hni"] = is_hni
            if lead.get("vip_category") != vip_cat:
                upd["vip_category"] = vip_cat

            # ── project field — ensure it exists (never overwrite real value) ──
            if "project" not in lead:
                upd["project"] = ""

            # ── Status from disposition (never overwrite existing status) ─
            curr_status  = lead.get("status") or ""
            disposition  = lead.get("disposition") or ""
            mapped_status = DISPOSITION_TO_STATUS.get(disposition, "")
            if mapped_status and curr_status in ("", None):
                upd["status"] = mapped_status

            # ── Temperature: set "Cold" for leads that have no temperature ─
            # These are failed / no-answer / busy calls where the seeder never
            # assigned a temperature. "Cold" is semantically correct for them.
            curr_temp = lead.get("temperature")
            if curr_temp is None or curr_temp == "":
                upd["temperature"] = "Cold"

            if upd:
                upd["updated_at"] = datetime.utcnow()
                ops.append(UpdateOne({"_id": oid}, {"$set": upd}))

        # ── Flush batch ──────────────────────────────────────────────────
        if ops:
            result = await db.leads.bulk_write(ops, ordered=False)
            updated += result.modified_count
            ops = []

        visited += len(batch)
        print(f"  Processed {visited}/{total} — modified so far: {updated}")
        skip += BATCH_SIZE

    print(f"\n{'='*60}")
    print(f"  Repair complete.")
    print(f"  Total visited : {visited}")
    print(f"  Total modified: {updated}")
    print(f"{'='*60}\n")

    client.close()


if __name__ == "__main__":
    asyncio.run(repair())
