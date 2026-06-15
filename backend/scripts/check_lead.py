import asyncio
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()
MONGO_URL = os.getenv("MONGO_URL", "")

async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client["rustomjee_db"]
    
    # Let's check the first one in the checkpoint list
    lead1 = await db.leads.find_one({"id": "58df85ab-fd3e-40cd-a781-4975c9cc4c94"})
    print("--- FIRST PROCESSED LEAD ---")
    if lead1:
        print('Qualification:', lead1.get('qualification_category'))
        print('Budget:', lead1.get('budget_category'))
        print('Temperature:', lead1.get('temperature'))
        print('Updated:', lead1.get('updated_at'))
    
    # Let's check a recent one
    lead2 = await db.leads.find_one({"id": "d8c97f8b-739c-483a-8758-5fe2966f93df"})
    print("\n--- RECENT PROCESSED LEAD ---")
    if lead2:
        print('Qualification:', lead2.get('qualification_category'))
        print('Budget:', lead2.get('budget_category'))
        print('Temperature:', lead2.get('temperature'))
        print('Updated:', lead2.get('updated_at'))
        
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
