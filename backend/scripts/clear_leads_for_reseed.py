"""
Clear lead-related MongoDB collections before a client_lead_id-only reseed.

**Destructive:** deletes all call_history (AI transcripts, recordings metadata).
Prefer: scripts/migrate_preserve_calls_and_seed.py (keeps calls, seeds 16k+ CSV).

Keeps users by default. Run from backend/:

  python scripts/clear_leads_for_reseed.py --dry-run
  python scripts/clear_leads_for_reseed.py

Then restart the API and run import_presales_leads_csv.py.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

load_dotenv()

COLLECTIONS = (
    "leads",
    "call_history",
    "lead_upload_history",
    "lead_upload_failures",
)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Clear lead data for client_lead_id reseed")
    parser.add_argument("--dry-run", action="store_true", help="Print counts only; do not delete")
    args = parser.parse_args()

    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "rustomjee_dash")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    counts = {}
    for name in COLLECTIONS:
        counts[name] = await db[name].count_documents({})

    print("Collections to clear:")
    for name in COLLECTIONS:
        print(f"  {name}: {counts[name]:,}")

    if args.dry_run:
        print("\nDry run — no documents deleted.")
        client.close()
        return

    for name in COLLECTIONS:
        result = await db[name].delete_many({})
        print(f"Deleted {result.deleted_count:,} from {name}")

    print("\nDone. Restart the API, then run import_presales_leads_csv.py.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
