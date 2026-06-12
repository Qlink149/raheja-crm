import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.getenv("MONGO_URL", "")
DB_NAME   = os.getenv("DB_NAME", "rustomjee_db")

async def run():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    q_missing_categories = {
        "$or": [
            {"qualification_category": {"$in": ["", None]}},
            {"temperature": {"$in": ["", None]}},
            {"budget_category": {"$in": ["", None]}}
        ]
    }
    
    total_missing = await db.leads.count_documents(q_missing_categories)
    print(f"Total leads missing categories: {total_missing}")
    
    q_missing_and_called = {
        **q_missing_categories,
        "last_call_status": {"$in": ["completed", "no-answer", "busy", "failed", "call-disconnected"]}
    }
    called_missing = await db.leads.count_documents(q_missing_and_called)
    print(f"Total leads missing categories that HAVE been called: {called_missing}")

    # Use aggregation to quickly find how many of these leads have transcripts
    pipeline = [
        {"$match": q_missing_and_called},
        {"$match": {"mobile_digits": {"$exists": True, "$ne": ""}}},
        {"$lookup": {
            "from": "call_history",
            "localField": "mobile_digits",
            "foreignField": "mobile_digits",
            "as": "calls"
        }},
        {"$project": {
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
        {"$count": "total_with_transcript"}
    ]
    
    result = await db.leads.aggregate(pipeline).to_list(1)
    leads_with_transcript = result[0]["total_with_transcript"] if result else 0
    print(f"Total leads missing categories that have a transcript available: {leads_with_transcript}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(run())
