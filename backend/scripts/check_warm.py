import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.environ.get("MONGO_URL", "")
DB_NAME   = os.environ.get("DB_NAME", "rustomjee_db")

async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    total = await db.leads.count_documents({})
    qc_warm = await db.leads.count_documents({"qualification_category": "Warm"})
    temp_warm = await db.leads.count_documents({"temperature": "Warm"})
    qc_hot = await db.leads.count_documents({"qualification_category": "Hot"})
    temp_hot = await db.leads.count_documents({"temperature": "Hot"})
    
    print(f"Total: {total}")
    print(f"QC Warm: {qc_warm}")
    print(f"Temp Warm: {temp_warm}")
    print(f"QC Hot: {qc_hot}")
    print(f"Temp Hot: {temp_hot}")
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
