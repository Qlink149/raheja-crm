import asyncio
import os
import pandas as pd
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv('.env')

CSV_DIR = r"c:\Users\Admin\Desktop\clara\Rustomjee_Dash-main\backend\csv"
MAIN_CSV1 = os.path.join(CSV_DIR, "rustomjee-lead-qualification-piya-2026-05-02-2026-05-08-ai_platform_call_history_report-230124c3-5000-431e-820d-e217b387b8fa.csv")
MAIN_CSV2 = os.path.join(CSV_DIR, "rustomjee-lead-qualification-piya-2026-05-27-2026-06-11-ai_platform_call_history_report-043ef4ab-7b44-4d48-85f5-5a0f5e7fc51a.csv")

async def analyze():
    client = AsyncIOMotorClient(os.getenv("MONGO_URL"))
    db = client["rustomjee_db"]
    
    print("Loading DB calls...")
    # Get all call IDs from DB
    db_calls = []
    async for c in db.call_history.find({}, {"id": 1, "call_sid": 1, "_id": 1}):
        db_calls.append(c.get("id") or c.get("call_sid") or str(c.get("_id")))
        
    db_call_set = set(db_calls)
    print(f"Loaded {len(db_call_set)} unique call IDs from DB.")
    
    print("Loading CSVs...")
    df1 = pd.read_csv(MAIN_CSV1, low_memory=False)
    df2 = pd.read_csv(MAIN_CSV2, low_memory=False)
    df_combined = pd.concat([df1, df2])
    
    missing_in_db = []
    
    for _, row in df_combined.iterrows():
        csv_id = row.get("_id")
        call_sid = row.get("callSid")
        
        # Check if either _id or callSid is in the DB
        if str(csv_id) not in db_call_set and str(call_sid) not in db_call_set:
            missing_in_db.append(row)
            
    print(f"Total calls in CSV but missing from DB: {len(missing_in_db)}")
    
    if missing_in_db:
        missing_df = pd.DataFrame(missing_in_db)
        print("\nBreakdown of missing calls by STATUS:")
        print(missing_df["status"].value_counts())
        
        print("\nBreakdown by DISPOSITION:")
        print(missing_df["disposition"].value_counts())
        
        print("\nLet's check phone numbers (first 10 missing rows):")
        for i, row in enumerate(missing_in_db[:10]):
            num = str(row.get("contextDetails_recipientPhoneNumber"))
            if pd.isna(num) or num == "nan":
                num = str(row.get("telephonyData_toNumber"))
            print(f"Row {i+1}: phone={num}, status={row.get('status')}")

    client.close()

if __name__ == "__main__":
    asyncio.run(analyze())
