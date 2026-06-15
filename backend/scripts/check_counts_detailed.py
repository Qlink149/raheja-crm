import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv('.env')

async def test():
    db = AsyncIOMotorClient(os.getenv('MONGO_URL'))['rustomjee_db']
    
    # Let's count leads missing categories that have a transcript
    count_missing = await db.leads.count_documents({
        "$or": [
            {"qualification_category": {"$in": ["", None]}},
            {"temperature": {"$in": ["", None]}}
        ],
        "transcript": {"$type": "string", "$ne": ""}
    })
    
    # And count how many of them are failing the last_call_status check
    count_wrong_status = await db.leads.count_documents({
        "$or": [
            {"qualification_category": {"$in": ["", None]}},
            {"temperature": {"$in": ["", None]}}
        ],
        "transcript": {"$type": "string", "$ne": ""},
        "last_call_status": {"$nin": ["completed", "no-answer", "busy", "failed", "call-disconnected"]}
    })
    
    print(f"Total uncategorized with transcripts: {count_missing}")
    print(f"How many blocked by last_call_status: {count_wrong_status}")

if __name__ == '__main__':
    asyncio.run(test())
