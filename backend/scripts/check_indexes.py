import asyncio
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv('.env')

async def test():
    client = AsyncIOMotorClient(os.getenv('MONGO_URL'))
    db = client['rustomjee_db']
    idx = await db.call_history.index_information()
    print(idx)

if __name__ == '__main__':
    asyncio.run(test())
