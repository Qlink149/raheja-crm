import asyncio
import os
import random
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv('../.env')

MONGO_URL = os.getenv('MONGO_URL', '')
DB_NAME = os.getenv('DB_NAME', 'rustomjee_db')

async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    print("Querying Dormant leads to find those that failed the leniency check...")
    
    pipeline = [
        {"$match": {"qualification_category": "Dormant", "mobile_digits": {"$exists": True, "$ne": ""}}},
        {"$lookup": {
            "from": "call_history",
            "localField": "mobile_digits",
            "foreignField": "mobile_digits",
            "as": "calls"
        }},
        {"$project": {
            "id": 1,
            "transcripts": {
                "$map": {
                    "input": "$calls",
                    "as": "call",
                    "in": "$$call.transcript"
                }
            }
        }}
    ]
    
    cursor = db.leads.aggregate(pipeline)
    
    failed_leads = []
    
    async for lead in cursor:
        lead_transcripts = [t for t in lead.get("transcripts", []) if t]
        if lead_transcripts:
            full_text = " ".join(lead_transcripts)
            word_count = len(full_text.split())
            
            # If word count > 50, it means it passed the pre-filter but was STILL rejected by OpenAI
            if word_count > 50:
                failed_leads.append(full_text)

    print(f"Found {len(failed_leads)} leads that had >50 words but were rejected by OpenAI.")
    print("========================================")
    print("Here are 3 random examples to see why the AI rejected them:")
    print("========================================\n")
    
    if failed_leads:
        samples = random.sample(failed_leads, min(3, len(failed_leads)))
        for i, text in enumerate(samples, 1):
            print(f"--- EXAMPLE {i} (Word count: {len(text.split())}) ---")
            # Print up to 1000 characters to avoid flooding the terminal
            safe_text = text.encode('cp1252', errors='replace').decode('cp1252')
            print(safe_text[:1000] + ("..." if len(safe_text) > 1000 else ""))
            print("\n")
    else:
        print("No failed leads found.")
        
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
