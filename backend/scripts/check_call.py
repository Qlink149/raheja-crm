import asyncio
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from motor.motor_asyncio import AsyncIOMotorClient

async def run():
    MONGO_URL = os.getenv("MONGO_URL", "")
    DB_NAME   = os.getenv("DB_NAME", "rustomjee_db")
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    call = await db.call_history.find_one()
    print(call.keys() if call else 'No calls')
    client.close()

if __name__ == "__main__":
    asyncio.run(run())
