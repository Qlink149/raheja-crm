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
    
    # Check leads that have missing categories
    q_missing_categories = {
        "$or": [
            {"qualification_category": {"$in": ["", None]}},
            {"temperature": {"$in": ["", None]}},
            {"budget_category": {"$in": ["", None]}}
        ]
    }
    
    total_missing = await db.leads.count_documents(q_missing_categories)
    print(f"Total leads missing categories: {total_missing}")
    
    # Check how many of those have actually been called
    q_missing_and_called = {
        **q_missing_categories,
        "last_call_status": {"$in": ["completed", "no-answer", "busy", "failed", "call-disconnected"]}
    }
    
    called_missing = await db.leads.count_documents(q_missing_and_called)
    print(f"Total leads missing categories that HAVE been called: {called_missing}")
    
    # Check how many of those called leads actually have a transcript in call_history
    cursor = db.leads.find(q_missing_and_called, {"id": 1, "mobile_digits": 1})
    leads = await cursor.to_list(length=100000)
    
    leads_with_transcript = 0
    for lead in leads:
        mobile_digits = lead.get("mobile_digits")
        if mobile_digits:
            call = await db.call_history.find_one({
                "mobile_digits": mobile_digits,
                "transcript": {"$type": "string", "$ne": ""}
            })
            if call:
                leads_with_transcript += 1
                
    print(f"Total leads missing categories that have a transcript available: {leads_with_transcript}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(run())
