import asyncio
import os
import json
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()
MONGO_URL = os.getenv("MONGO_URL", "")

async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client["rustomjee_db"]
    
    count = await db.leads.count_documents({
        "qualification_category": {"$nin": ["", None]}
    })
    print('Total Categorized leads count in DB:', count)
    
    # Check what kind of failures we have by getting transcripts of recent failures
    with open('scripts/backfill_checkpoint.json') as f:
        data = json.load(f)
    
    processed = data['processed_ids']
    # Just look at the last 100
    recent_100 = processed[-100:]
    
    success_in_recent = 0
    fail_in_recent = 0
    
    for lid in recent_100:
        lead = await db.leads.find_one({"id": lid})
        if not lead:
            continue
            
        qual = lead.get('qualification_category')
        if qual and qual.strip() != "":
            success_in_recent += 1
        else:
            fail_in_recent += 1
            print(f"Failed Lead {lid}: Transcript snippet: {str(lead.get('calls', [{}])[0].get('transcript', ''))[:100]}")
            
    print(f"\nOut of last 100 processed, actually categorized in DB: {success_in_recent}")
    print(f"Failed to categorize: {fail_in_recent}")
        
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
