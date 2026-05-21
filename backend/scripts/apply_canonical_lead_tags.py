"""
Apply canonical qualification_category from match flags; clear legacy temperature.

Usage (from backend/):
  python scripts/apply_canonical_lead_tags.py --dry-run
  python scripts/apply_canonical_lead_tags.py
  python scripts/apply_canonical_lead_tags.py --upload-batch-name "test 21 may"
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
)
from app.utils.lead_tag_sync import is_non_contactable_status  # noqa: E402

load_dotenv()


async def run(
    *,
    dry_run: bool,
    limit: int,
    batch_name: str,
    source: str,
) -> None:
    mongo_url = os.environ.get("MONGO_URL", "")
    db_name = os.environ.get("DB_NAME", "rustomjee_db")
    if not mongo_url:
        print("MONGO_URL is not set.")
        sys.exit(1)

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    query: dict = {}
    if batch_name:
        query["upload_batch_name"] = batch_name
    if source:
        query["source"] = source

    cursor = db.leads.find(
        query,
        {
            "_id": 1,
            "id": 1,
            "full_name": 1,
            "status": 1,
            "temperature": 1,
            "qualification_category": 1,
            "budget_match": 1,
            "area_match": 1,
            "timeline_match": 1,
            "budget_category": 1,
        },
    ).limit(limit)
    docs = await cursor.to_list(limit)

    ops = []
    skipped = 0
    for doc in docs:
        status = str(doc.get("status") or "")
        if is_non_contactable_status(status):
            patch = canonical_lead_tags_from_doc(doc)
        elif has_match_flags(doc):
            patch = canonical_lead_tags_from_doc(doc)
        else:
            skipped += 1
            continue

        if not patch:
            skipped += 1
            continue

        patch["updated_at"] = utc_now()
        ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": patch}))
        print(
            f"{'[dry-run] ' if dry_run else ''}{doc.get('full_name') or doc.get('id')} | "
            f"qc={patch.get('qualification_category', '(cleared)')} | temp cleared"
        )

    print(f"To update: {len(ops)} | Skipped (no flags / non-actionable): {skipped}")
    if ops and not dry_run:
        result = await db.leads.bulk_write(ops, ordered=False)
        print(f"Modified: {result.modified_count}")

    client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply canonical lead qualification tags")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=100000)
    parser.add_argument("--upload-batch-name", type=str, default="")
    parser.add_argument("--source", type=str, default="")
    args = parser.parse_args()
    asyncio.run(
        run(
            dry_run=args.dry_run,
            limit=max(1, args.limit),
            batch_name=(args.upload_batch_name or "").strip(),
            source=(args.source or "").strip(),
        )
    )


if __name__ == "__main__":
    main()
