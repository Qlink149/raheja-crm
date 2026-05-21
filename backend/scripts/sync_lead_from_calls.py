"""
Copy best structured_extraction from call_history onto a lead (no OpenAI).

Usage:
  python scripts/sync_lead_from_calls.py --lead-id 201c3c72-74f4-4030-a16b-2b43d5e4577f
  python scripts/sync_lead_from_calls.py --name Mini
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.time_utils import utc_now  # noqa: E402
from app.services.structured_ai_service import StructuredAIService  # noqa: E402
from app.utils.lead_qualification_tags import apply_canonical_tags_to_lead_patch  # noqa: E402
from app.utils.orphan_call_link import structured_extraction_from_call  # noqa: E402

load_dotenv()


async def run(*, lead_id: str, name: str, dry_run: bool) -> None:
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
        flt["full_name"] = {"$regex": f"^{name}$", "$options": "i"}
    else:
        print("Provide --lead-id or --name")
        sys.exit(1)

    lead = await db.leads.find_one(flt, {"_id": 0})
    if not lead:
        print("Lead not found:", flt)
        sys.exit(1)

    lid = lead["id"]
    calls = await db.call_history.find({"lead_id": lid}, {"_id": 0}).sort("created_at", -1).to_list(500)

    best_ex = None
    best_call = None
    best_score = -1
    for ch in calls:
        ex = structured_extraction_from_call(ch)
        if not ex:
            continue
        score = int(ex.budget_match) + int(ex.area_match) + int(ex.timeline_match)
        if score > best_score:
            best_score = score
            best_ex = ex
            best_call = ch

    if not best_ex or not best_call:
        print(f"No structured_extraction on {len(calls)} calls for {lead.get('full_name')} ({lid})")
        client.close()
        sys.exit(1)

    patch = apply_canonical_tags_to_lead_patch(svc.to_db_lead_patch_unified(best_ex), lead)
    patch["updated_at"] = utc_now()
    print(
        f"{lead.get('full_name')} | from call {best_call.get('id')} | "
        f"qc={patch.get('qualification_category')} | "
        f"budget_match={patch.get('budget_match')} area_match={patch.get('area_match')} "
        f"timeline_match={patch.get('timeline_match')}"
    )
    if not dry_run:
        await db.leads.update_one(
            {"id": lid},
            {"$set": patch, "$unset": {"aiPersonaSummary": "", "strategicNextMove": ""}},
        )
        print("Updated lead.")
    else:
        print("[dry-run] No DB write.")

    client.close()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--lead-id", default="")
    p.add_argument("--name", default="")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    asyncio.run(run(lead_id=args.lead_id.strip(), name=args.name.strip(), dry_run=args.dry_run))


if __name__ == "__main__":
    main()
