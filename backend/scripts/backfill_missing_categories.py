import asyncio
import os
import sys
import logging
import argparse
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app.services.structured_ai_service import StructuredAIService

MONGO_URL = os.getenv("MONGO_URL", "")
DB_NAME   = os.getenv("DB_NAME", "rustomjee_db")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

async def run(dry_run: bool, limit: int):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    ai_service = StructuredAIService(db)
    
    print("=" * 70)
    print(f"  FAST MISSING CATEGORY BACKFILL SCRIPT {'(DRY RUN)' if dry_run else ''}")
    print("=" * 70)
    print("Step 1: Running fast database aggregation to find leads with transcripts...")
    print("Please wait a few seconds...\n")

    q_missing_categories = {
        "$or": [
            {"qualification_category": {"$in": ["", None]}},
            {"temperature": {"$in": ["", None]}},
            {"budget_category": {"$in": ["", None]}}
        ],
        "last_call_status": {"$in": ["completed", "no-answer", "busy", "failed", "call-disconnected"]}
    }

    # Use MongoDB Aggregation to get exactly the leads that HAVE a transcript.
    # This avoids doing 12,000 individual queries in a for loop.
    pipeline = [
        {"$match": q_missing_categories},
        {"$match": {"mobile_digits": {"$exists": True, "$ne": ""}}},
        {"$lookup": {
            "from": "call_history",
            "localField": "mobile_digits",
            "foreignField": "mobile_digits",
            "as": "calls"
        }},
        {"$project": {
            "id": 1,
            "has_transcript": {
                "$gt": [{
                    "$size": {
                        "$filter": {
                            "input": "$calls",
                            "as": "call",
                            "cond": {
                                "$and": [
                                    {"$ne": ["$$call.transcript", None]},
                                    {"$ne": ["$$call.transcript", ""]}
                                ]
                            }
                        }
                    }
                }, 0]
            }
        }},
        {"$match": {"has_transcript": True}},
        {"$limit": limit}
    ]

    cursor = db.leads.aggregate(pipeline)
    eligible_lead_ids = []
    async for doc in cursor:
        eligible_lead_ids.append(doc["id"])
        
    count = len(eligible_lead_ids)
    print(f"Found {count} leads that are perfectly eligible for AI extraction!")
    print("-" * 70)

    if count == 0:
        print("No leads found. Exiting.")
        client.close()
        return

    if dry_run:
        print(f"Dry run enabled. Would perform exactly {count} LLM calls via StructuredAIService.")
        print(f"Run without --dry-run to begin executing the extractions.")
        client.close()
        return

    # Execution Phase
    print("\nPHASE 2: Executing AI Extractions...")
    success_count = 0
    fail_count = 0
    
    for i, lead_id in enumerate(eligible_lead_ids):
        # Progress bar
        if i % 10 == 0:
            print(f"  [Progress] Processed {i}/{count} leads... (Success: {success_count}, Failed: {fail_count})")
            
        try:
            res = await ai_service.generate_call_summary_unified(lead_id=lead_id, refresh=True)
            if res and "not contain enough actionable" not in res:
                success_count += 1
            else:
                fail_count += 1
        except Exception as e:
            fail_count += 1
            
    print(f"  [Progress] Processed {count}/{count} leads... DONE.")
    print("-" * 70)
    print(f"Finished execution.")
    print(f"Successfully extracted categories for: {success_count} leads")
    print(f"Skipped / Failed for: {fail_count} leads")
        
    client.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill missing categories on leads using AI.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without making changes.")
    parser.add_argument("--limit", type=int, default=15000, help="Maximum number of leads to process.")
    args = parser.parse_args()
    
    asyncio.run(run(dry_run=args.dry_run, limit=args.limit))
