import asyncio
import pandas as pd
import uuid
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os
import sys

# Add the current directory to sys.path so we can import from app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.utils.csv_processor import process_row_to_lead

load_dotenv()

async def seed():
    mongo_url = os.getenv("MONGO_URL")
    db_name = os.getenv("DB_NAME")
    
    if not mongo_url or not db_name:
        print("❌ Error: MONGO_URL or DB_NAME not found in .env")
        return

    print("🔌 Connecting to MongoDB...")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    # Process all 3 files
    files = [
        "data/leads_data.csv", 
        "data/leads.csv", 
        "data/lead_dump.csv"
    ]
    
    total_inserted = 0
    
    for file in files:
        if not os.path.exists(file):
            print(f"⚠️ Skipping {file} (File not found)")
            continue
            
        print(f"\n📂 Processing {file}...")
        try:
            # Read CSV and handle NaN values
            df = pd.read_csv(file, low_memory=False)
            df = df.fillna("")
            records = df.to_dict("records")
            
            leads_to_insert = []
            for row in records:
                # Map CSV columns to Database Schema
                lead = process_row_to_lead(row)
                lead["id"] = str(uuid.uuid4())
                leads_to_insert.append(lead)
                
            if leads_to_insert:
                print(f"⏳ Pushing {len(leads_to_insert)} records to DB in chunks...")
                chunk_size = 5000
                for i in range(0, len(leads_to_insert), chunk_size):
                    chunk = leads_to_insert[i:i+chunk_size]
                    await db.leads.insert_many(chunk)
                print(f"✅ Successfully inserted {len(leads_to_insert)} leads from {file}!")
                total_inserted += len(leads_to_insert)
        
        except Exception as e:
            print(f"❌ Error processing {file}: {e}")

    print(f"\n🎉 All done! Total leads seeded to database: {total_inserted}")

if __name__ == "__main__":
    asyncio.run(seed())
