"""
Repair leads: clear tags for non-contactable; apply canonical QC for mismatched rows.

Prefer: python scripts/apply_canonical_lead_tags.py for full DB recompute.
This script targets non-contactable rows and legacy Warm/Hot temperature noise.

Usage (from backend/):
  python scripts/repair_lead_temperature_status.py --dry-run
  python scripts/repair_lead_temperature_status.py
  python scripts/repair_lead_temperature_status.py --upload-batch-name "test 21 may"
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.time_utils import utc_now  # noqa: E402
from app.utils.lead_qualification_tags import (  # noqa: E402
    canonical_lead_tags_from_doc,
    has_match_flags,
    is_non_contactable_status,
    non_contactable_tag_patch,
)

load_dotenv()

MONGO_URL = os.environ.get("MONGO_URL", "")
DB_NAME = os.environ.get("DB_NAME", "rustomjee_db")


async def run(*, dry_run: bool, batch_name: str, limit: int) -> None:
    if not MONGO_URL:
        print("MONGO_URL is not set.")
        sys.exit(1)

    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    # Broad scan: non-contactable-like status OR legacy Hot/Warm (re-checked in Python).
    query: dict = {
        "$or": [
            {"status": {"$regex": r"non[\s-]*contactable", "$options": "i"}},
            {"status": {"$regex": r"^lost$", "$options": "i"}},
            {"status": {"$regex": r"^dnc$", "$options": "i"}},
            {"temperature": {"$in": ["Hot", "Warm"]}},
        ]
    }
    if batch_name:
        query["upload_batch_name"] = batch_name

    cursor = db.leads.find(
        query,
        {"_id": 1, "id": 1, "status": 1, "temperature": 1, "full_name": 1},
    ).limit(limit)
    docs = await cursor.to_list(limit)

    ops = []
    for doc in docs:
        status = str(doc.get("status") or "")
        if is_non_contactable_status(status):
            patch = {**non_contactable_tag_patch(), "updated_at": utc_now()}
        elif has_match_flags(doc):
            patch = {**canonical_lead_tags_from_doc(doc), "updated_at": utc_now()}
        elif str(doc.get("temperature") or "") in ("Hot", "Warm"):
            patch = {"temperature": "", "updated_at": utc_now()}
        else:
            continue
        ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": patch}))
        print(
            f"{'[dry-run] ' if dry_run else ''}lead={doc.get('id')} "
            f"name={doc.get('full_name') or '—'} status={status} | patch={patch}"
        )

    print(f"Candidates to fix: {len(ops)}")
    if ops and not dry_run:
        result = await db.leads.bulk_write(ops, ordered=False)
        print(f"Modified: {result.modified_count}")
    elif not ops:
        # Helpful when re-running after a successful repair (0 is expected, not an error).
        batch_filter = {"upload_batch_name": batch_name} if batch_name else {}
        scanned = await db.leads.find(
            batch_filter or {},
            {"_id": 0, "id": 1, "full_name": 1, "status": 1, "temperature": 1},
        ).limit(20).to_list(20)
        if batch_name:
            print(f"No changes needed for batch '{batch_name}'.")
        else:
            print("No changes needed.")
        if scanned:
            print("Sample leads in scope:")
            for row in scanned:
                print(
                    f"  - {row.get('full_name') or '—'} | status={row.get('status') or '—'} "
                    f"| temperature={row.get('temperature') if row.get('temperature') not in (None, '') else '(missing)'}"
                )
        else:
            print("No leads matched the batch filter. Check --upload-batch-name spelling.")

    client.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Set temperature=Cold when CRM status is non-contactable"
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--upload-batch-name", type=str, default="")
    parser.add_argument("--limit", type=int, default=50000)
    args = parser.parse_args()
    asyncio.run(
        run(
            dry_run=args.dry_run,
            batch_name=(args.upload_batch_name or "").strip(),
            limit=max(1, args.limit),
        )
    )


if __name__ == "__main__":
    main()
