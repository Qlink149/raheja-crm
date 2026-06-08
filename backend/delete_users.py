import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

async def main():
    load_dotenv()
    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "rustomjee_crm")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    emails_to_delete = [
        "kishore@rustomjee.com", 
        "elton@rustomjee.com", 
        "tejal@rustomjee.com11"
    ]
    
    result = await db.users.delete_many({"email": {"$in": emails_to_delete}})
    print(f"Deleted {result.deleted_count} user(s) from the database.")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
