import argparse
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

MONGO_URL = os.environ.get("MONGO_URL", "")
DB_NAME   = os.environ.get("DB_NAME", "rustomjee_db")

BATCH_SIZE = 500

async def migrate(dry_run: bool):
    if not MONGO_URL:
        print("MONGO_URL not found in environment.")
        return

    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    total = await db.leads.count_documents({})
    print(f"\n{'='*60}")
    print(f"  Migration starting — {total} leads in {DB_NAME}")
    if dry_run:
        print("  MODE: DRY RUN (No database changes will be made)")
    print(f"{'='*60}\n")

    skip = 0
    ops = []
    updated = 0
    visited = 0

    while True:
        batch = await db.leads.find(
            {},
            {
                "_id": 1,
                "qualification_category": 1,
                "temperature": 1,
            },
        ).skip(skip).limit(BATCH_SIZE).to_list(BATCH_SIZE)

        if not batch:
            break

        for lead in batch:
            oid = lead["_id"]
            upd: dict = {}

            qc = lead.get("qualification_category", "")
            temp = lead.get("temperature", "")

            new_qc = qc
            new_temp = temp

            # 1. Hot -> Warm
            if qc == "Hot":
                new_qc = "Warm"
            if temp == "Hot":
                new_temp = "Warm"

            # 2. VIP Pipeline -> Hot
            # Note: We do this after Hot->Warm to avoid converting a VIP->Hot->Warm in one pass.
            if qc == "VIP Pipeline":
                new_qc = "Hot"
            if temp == "VIP Pipeline" or temp == "VIP":
                new_temp = "Hot"

            if new_qc != qc:
                upd["qualification_category"] = new_qc
            if new_temp != temp:
                upd["temperature"] = new_temp

            if upd:
                upd["updated_at"] = datetime.utcnow()
                ops.append(UpdateOne({"_id": oid}, {"$set": upd}))

        # Flush batch
        if ops:
            if not dry_run:
                result = await db.leads.bulk_write(ops, ordered=False)
                updated += result.modified_count
            else:
                updated += len(ops)
            ops = []

        visited += len(batch)
        print(f"  Processed {visited}/{total} — {'would modify' if dry_run else 'modified'} so far: {updated}")
        skip += BATCH_SIZE

    print(f"\n{'='*60}")
    print(f"  Migration complete.")
    print(f"  Total visited : {visited}")
    print(f"  Total {'would be modified' if dry_run else 'modified'}: {updated}")
    print(f"{'='*60}\n")

    client.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate VIP leads to Hot, and Hot to Warm.")
    parser.add_argument("--dry-run", action="store_true", help="Run without applying changes")
    args = parser.parse_args()

    asyncio.run(migrate(dry_run=args.dry_run))
