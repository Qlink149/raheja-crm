"""
Merge duplicate lead documents that share the same mobile_digits, then a unique
index on mobile_digits can be created (see initialize_db in app/core/database.py).

  cd backend
  python scripts/dedupe_leads_by_mobile.py --dry-run
  python scripts/dedupe_leads_by_mobile.py --execute
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))


def _merge_docs(canonical: Dict[str, Any], other: Dict[str, Any]) -> Dict[str, Any]:
    """Fill empty / missing fields on canonical from other (prefer canonical non-empty)."""
    out = dict(canonical)
    for k, v in other.items():
        if k == "_id":
            continue
        if k in ("id", "created_at"):
            continue
        cur = out.get(k)
        empty = cur is None or cur == ""
        if empty and v not in (None, ""):
            out[k] = v
    out["updated_at"] = datetime.utcnow()
    return out


async def run(*, dry_run: bool) -> None:
    mongo_url = os.environ.get("MONGO_URL", "").strip()
    db_name = os.environ.get("DB_NAME", "rustomjee_db").strip() or "rustomjee_db"
    if not mongo_url:
        raise SystemExit("MONGO_URL is not set")

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    leads = db.leads

    all_docs = await leads.find(
        {"mobile_digits": {"$nin": [None, ""]}},
        {"_id": 1, "mobile_digits": 1},
    ).to_list(None)
    by_digits: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for d in all_docs:
        md = (d.get("mobile_digits") or "").strip()
        if md:
            by_digits[md].append(d)

    dup_groups = {k: v for k, v in by_digits.items() if len(v) > 1}
    print(f"Unique mobile_digits with duplicates: {len(dup_groups)}")
    total_extra = sum(len(v) - 1 for v in dup_groups.values())
    print(f"Extra documents to remove (after merge): {total_extra}")

    merged = 0
    deleted = 0
    for md, oid_list in dup_groups.items():
        full_docs = []
        for d in oid_list:
            doc = await leads.find_one({"_id": d["_id"]})
            if doc:
                full_docs.append(doc)
        if len(full_docs) < 2:
            continue
        full_docs.sort(
            key=lambda x: (x.get("updated_at") or x.get("created_at") or datetime.min),
            reverse=True,
        )
        keeper = full_docs[0]
        merged_body = dict(keeper)
        for other in full_docs[1:]:
            merged_body = _merge_docs(merged_body, other)
        merged_body["mobile_digits"] = md

        if dry_run:
            print(f"[dry-run] {md}: keep {keeper.get('id')} merge {len(full_docs) - 1} dupes")
            merged += 1
            continue

        await leads.replace_one({"_id": keeper["_id"]}, merged_body)
        for other in full_docs[1:]:
            await leads.delete_one({"_id": other["_id"]})
            deleted += 1
        merged += 1

    client.close()
    if dry_run:
        print("Dry run complete. Re-run with --execute to apply.")
    else:
        print(f"Merged {merged} groups, deleted {deleted} duplicate documents.")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", dest="dry_run")
    p.add_argument("--execute", action="store_true", dest="execute")
    args = p.parse_args()
    dry = not args.execute
    if args.dry_run and args.execute:
        p.error("Use only one of --dry-run or --execute")
    asyncio.run(run(dry_run=dry))


if __name__ == "__main__":
    main()
