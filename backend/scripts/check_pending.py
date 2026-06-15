import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv('.env')

async def test():
    db = AsyncIOMotorClient(os.getenv('MONGO_URL'))['rustomjee_db']
    pending = await db.leads.count_documents({'futwork_sync_status': 'pending'})
    print(f'Remaining Pending: {pending}')

if __name__ == '__main__':
    asyncio.run(test())
