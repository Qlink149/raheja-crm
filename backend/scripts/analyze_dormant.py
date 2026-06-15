import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv('../.env')

MONGO_URL = os.getenv('MONGO_URL', '')
DB_NAME = os.getenv('DB_NAME', 'rustomjee_db')

async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    print("Querying Dormant leads with transcripts...")
    
    # We want leads that are Dormant
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
                    "in": {"transcript": "$$call.transcript", "status": "$$call.call_status"}
                }
            }
        }}
    ]
    
    cursor = db.leads.aggregate(pipeline)
    
    total_dormant = 0
    with_transcripts = 0
    
    # Bins for transcript length
    len_bins = {"0-50": 0, "51-200": 0, "201-500": 0, "500+": 0}
    longest_transcript = ""
    
    async for lead in cursor:
        total_dormant += 1
        lead_transcripts = [t["transcript"] for t in lead.get("transcripts", []) if t.get("transcript")]
        if lead_transcripts:
            with_transcripts += 1
            # Combine all transcripts for this lead
            full_text = " | ".join(lead_transcripts)
            char_len = len(full_text)
            
            if char_len > len(longest_transcript):
                longest_transcript = full_text
                
            if char_len <= 50:
                len_bins["0-50"] += 1
            elif char_len <= 200:
                len_bins["51-200"] += 1
            elif char_len <= 500:
                len_bins["201-500"] += 1
            else:
                len_bins["500+"] += 1

    print("========================================")
    print(f"Total Dormant Leads Processed: {total_dormant}")
    print(f"Dormant Leads with ANY Transcript: {with_transcripts}")
    print("\nTranscript Length Breakdown (in characters):")
    for b, count in len_bins.items():
        print(f"  {b} chars : {count} leads")
        
    print("\n========================================")
    print("EXAMPLE: Longest 'Dormant' Transcript found:")
    print("----------------------------------------")
    if longest_transcript:
        # truncate to 1000 chars for console readability
        print(longest_transcript[:1000] + ("..." if len(longest_transcript) > 1000 else ""))
    else:
        print("None found.")
    print("========================================")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
