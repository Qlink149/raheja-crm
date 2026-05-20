"""
One-time cleanup: remove lead_upload_history rows that were never pushed to Futwork.

Run once after deploying Futwork-only history rules:
  cd backend
  python scripts/prune_non_futwork_upload_history.py --dry-run
  python scripts/prune_non_futwork_upload_history.py

Requires MONGO_URL and DB_NAME in backend/.env (same as the API).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from motor.motor_asyncio import AsyncIOMotorClient

NON_FUTWORK_QUERY = {
    "$or": [
        {"futwork_pushed": {"$exists": False}},
        {"futwork_pushed": 0},
    ]
}


async def run(dry_run: bool) -> None:
    if not settings.MONGO_URL:
        print("MONGO_URL is not set. Configure backend/.env first.")
        sys.exit(1)

    client = AsyncIOMotorClient(settings.MONGO_URL)
    db = client[settings.DB_NAME]

    to_delete = await db.lead_upload_history.count_documents(NON_FUTWORK_QUERY)
    print(f"lead_upload_history rows to remove (futwork_pushed <= 0): {to_delete}")

    if dry_run:
        print("Dry run — no changes made.")
        client.close()
        return

    if to_delete:
        result = await db.lead_upload_history.delete_many(NON_FUTWORK_QUERY)
        print(f"Deleted {result.deleted_count} history document(s).")

    remaining_ids = [
        d["id"]
        async for d in db.lead_upload_history.find({}, {"_id": 0, "id": 1})
        if d.get("id")
    ]
    orphan_filter = {"upload_id": {"$nin": remaining_ids}} if remaining_ids else {}
    orphan_count = await db.lead_upload_failures.count_documents(orphan_filter)
    print(f"lead_upload_failures orphan rows (upload_id not in history): {orphan_count}")

    if orphan_count and not dry_run:
        orphan_result = await db.lead_upload_failures.delete_many(orphan_filter)
        print(f"Deleted {orphan_result.deleted_count} orphan failure row(s).")

    client.close()
    print("Done.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count only; do not delete",
    )
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
