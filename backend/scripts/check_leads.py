import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from collections import Counter

load_dotenv('../.env')

MONGO_URL = os.getenv('MONGO_URL', '')
DB_NAME = os.getenv('DB_NAME', 'rustomjee_db')

async def main():
    if not MONGO_URL:
        print("MONGO_URL not found in environment")
        return

    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    print("Fetching lead statistics...")
    
    # Fetch all leads and their relevant fields
    cursor = db.leads.find({}, {"qualification_category": 1, "temperature": 1})
    leads = await cursor.to_list(length=None)
    
    print(f"Total leads in database: {len(leads)}\n")
    
    qual_counter = Counter(lead.get("qualification_category") for lead in leads)
    temp_counter = Counter(lead.get("temperature") for lead in leads)
    
    print("--- Leads by Qualification Category ---")
    for category, count in qual_counter.items():
        print(f"{category}: {count}")
        
    print("\n--- Leads by Temperature ---")
    for temp, count in temp_counter.items():
        print(f"{temp}: {count}")

    print("\n--- Leads Grouped by (Category, Temperature) ---")
    combo_counter = Counter((lead.get("qualification_category"), lead.get("temperature")) for lead in leads)
    for (category, temp), count in combo_counter.items():
        print(f"Category: {category} | Temperature: {temp} -> {count} leads")
        
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
