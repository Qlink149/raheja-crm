import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os
import json
from bson import ObjectId

class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        return json.JSONEncoder.default(self, o)

async def main():
    load_dotenv()
    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "rustomjee_crm")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    users = await db.users.find().to_list(length=None)
    for u in users:
        u.pop("hashed_password", None)
        u.pop("_id", None)
    with open("users_dump_utf8.json", "w", encoding="utf-8") as f:
        json.dump(users, f, cls=JSONEncoder, indent=2)
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
