import asyncio
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv('.env')

async def inspect():
    client = AsyncIOMotorClient(os.getenv("MONGO_URL"))
    db = client["rustomjee_db"]
    
    # Get a real sample from call_history to understand schema
    sample = await db.call_history.find_one({"transcript": {"$ne": None, "$ne": ""}})
    if sample:
        print("call_history fields:")
        for k, v in sample.items():
            val_preview = str(v)[:80] if v is not None else "None"
            print(f"  {k}: {val_preview}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(inspect())
