import asyncio
import os
import sys
import argparse
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.getenv("MONGO_URL", "")
DB_NAME   = os.getenv("DB_NAME", "rustomjee_db")

async def run(dry_run: bool):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    q = {
        "futwork_sync_status": {"$in": ["pending", "failed", None]},
        "last_call_status": {"$in": ["completed", "no-answer", "busy", "failed", "call-disconnected", "no_answer"]},
        "client_lead_id": {"$exists": True, "$nin": ["", None]},
    }
    
    count = await db.leads.count_documents(q)
    print("=" * 70)
    print(f"  FIX PENDING CALLED SCRIPT {'(DRY RUN)' if dry_run else ''}")
    print("=" * 70)
    print(f"Found {count} leads that have already been called but are stuck in pending/failed status.")
    
    if count > 0:
        if dry_run:
            print(f"Dry run enabled. Would update {count} leads to futwork_sync_status = 'pushed'.")
        else:
            result = await db.leads.update_many(
                q,
                {"$set": {"futwork_sync_status": "pushed"}}
            )
            print(f"Updated {result.modified_count} leads to futwork_sync_status = 'pushed'")
    
    client.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fix stuck pending leads.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without making changes.")
    args = parser.parse_args()
    
    asyncio.run(run(dry_run=args.dry_run))
