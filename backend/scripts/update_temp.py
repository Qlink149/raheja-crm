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

    print("Updating temperatures based on qualification_category...")

    hot_result = await db.leads.update_many(
        {"qualification_category": "Hot"},
        {"$set": {"temperature": "Hot"}}
    )
    print(f"Updated {hot_result.modified_count} Hot leads.")

    warm_result = await db.leads.update_many(
        {"qualification_category": "Warm"},
        {"$set": {"temperature": "Warm"}}
    )
    print(f"Updated {warm_result.modified_count} Warm leads.")

    qualified_result = await db.leads.update_many(
        {"qualification_category": "Qualified"},
        {"$set": {"temperature": "Qualified"}}
    )
    print(f"Updated {qualified_result.modified_count} Qualified leads.")

    client.close()

if __name__ == "__main__":
    asyncio.run(main())
