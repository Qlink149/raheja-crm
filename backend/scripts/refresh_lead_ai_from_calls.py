#!/usr/bin/env python3
"""
Re-run unified AI extraction for a lead's call(s) (budget + call summary).

Usage:
  python scripts/refresh_lead_ai_from_calls.py --name Siddharth
  python scripts/refresh_lead_ai_from_calls.py --lead-id <uuid>
  python scripts/refresh_lead_ai_from_calls.py --lead-id <uuid> --call-sid <callSid>
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.structured_ai_service import StructuredAIService  # noqa: E402

load_dotenv()


async def run(*, lead_id: str, name: str, call_sid: str | None) -> None:
    mongo_url = os.environ.get("MONGO_URL", "")
    db_name = os.environ.get("DB_NAME", "rustomjee_db")
    if not mongo_url:
        print("MONGO_URL is not set.")
        sys.exit(1)

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    svc = StructuredAIService(db)

    flt: dict = {}
    if lead_id:
        flt["id"] = lead_id
    elif name:
        flt["full_name"] = {"$regex": name.strip(), "$options": "i"}
    else:
        print("Provide --lead-id or --name")
        sys.exit(1)

    lead = await db.leads.find_one(flt, {"_id": 0})
    if not lead:
        print("Lead not found.")
        sys.exit(1)

    lid = str(lead["id"])
    print(f"Lead: {lead.get('full_name')} | id={lid} | budget_before={lead.get('budget')!r}")

    if call_sid:
        summary = await svc.generate_call_summary_unified(lid, call_sid=call_sid, refresh=True)
        print(f"Refreshed call_sid={call_sid}")
        print(f"Summary: {summary[:200]}...")
    else:
        md = (lead.get("mobile_digits") or "").strip()
        if not md:
            print("Lead has no mobile_digits.")
            sys.exit(1)
        calls = await db.call_history.find({"mobile_digits": md}).sort("created_at", -1).to_list(10)
        if not calls:
            print("No call_history rows.")
            sys.exit(1)
        for doc in calls:
            cid = doc.get("id") or doc.get("call_sid")
            if not cid:
                continue
            dur = int(doc.get("duration") or 0)
            print(f"Refreshing call {cid} (duration={dur}s)...")
            summary = await svc.generate_call_summary_unified(lid, call_sid=str(cid), refresh=True)
            print(f"  -> {summary[:120]}...")

    lead_after = await db.leads.find_one({"id": lid}, {"_id": 0, "budget": 1, "budget_category": 1})
    print(f"budget_after={lead_after.get('budget')!r} category={lead_after.get('budget_category')!r}")
    client.close()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--lead-id", default="")
    p.add_argument("--name", default="")
    p.add_argument("--call-sid", default="")
    args = p.parse_args()
    asyncio.run(
        run(
            lead_id=(args.lead_id or "").strip(),
            name=(args.name or "").strip(),
            call_sid=(args.call_sid or "").strip() or None,
        )
    )


if __name__ == "__main__":
    main()
