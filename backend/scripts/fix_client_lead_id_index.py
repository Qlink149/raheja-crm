"""One-shot: replace sparse unique client_lead_id index with required non-sparse unique."""
from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_SCRIPT_DIR, ".."))
sys.path.insert(0, _SCRIPT_DIR)

load_dotenv()


async def main() -> None:
    from migrate_preserve_calls_and_seed import ensure_post_migration_indexes

    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "rustomjee_dash")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    missing = await db.leads.count_documents(
        {"$or": [{"client_lead_id": {"$exists": False}}, {"client_lead_id": {"$in": [None, ""]}}]}
    )
    if missing:
        print(f"WARN: {missing} leads missing client_lead_id — fix before non-sparse unique index.")
    else:
        print(f"OK: all {await db.leads.count_documents({})} leads have client_lead_id")

    await ensure_post_migration_indexes(db, dry_run=False)
    print("Done.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
