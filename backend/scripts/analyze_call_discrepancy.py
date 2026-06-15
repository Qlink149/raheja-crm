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
    
    # 1. Count DB call_history records
    db_calls = await db.call_history.count_documents({})
    print(f"Total call_history in DB: {db_calls}")
    
    # 2. Load CSVs and analyze uniqueness
    print("Loading CSVs...")
    df1 = pd.read_csv(MAIN_CSV1, low_memory=False)
    df2 = pd.read_csv(MAIN_CSV2, low_memory=False)
    
    total_rows = len(df1) + len(df2)
    print(f"Total rows in CSV files: {total_rows}")
    
    # Analyze df1
    df1_unique_ids = df1["_id"].nunique()
    print(f"CSV1 rows: {len(df1)}, unique _id: {df1_unique_ids}")
    
    # Analyze df2
    df2_unique_ids = df2["_id"].nunique()
    print(f"CSV2 rows: {len(df2)}, unique _id: {df2_unique_ids}")
    
    # Combine and analyze global uniqueness
    df_combined = pd.concat([df1, df2])
    global_unique_ids = df_combined["_id"].nunique()
    print(f"Combined unique _id across both CSVs: {global_unique_ids}")
    
    # Let's count unique callSid
    global_unique_call_sid = df_combined["callSid"].nunique()
    print(f"Combined unique callSid across both CSVs: {global_unique_call_sid}")
    
    # Let's count how many have valid phone numbers
    def extract_phone(row):
        num = str(row.get("contextDetails_recipientPhoneNumber"))
        if pd.isna(num) or num == "nan":
            num = str(row.get("telephonyData_toNumber"))
        if pd.isna(num) or num == "nan":
            return None
        digits = "".join([c for c in str(num) if c.isdigit()])
        if len(digits) > 10 and digits.startswith("91"):
            digits = digits[2:]
        if len(digits) == 10:
            return digits
        return None
        
    df_combined["parsed_phone"] = df_combined.apply(extract_phone, axis=1)
    valid_phones = df_combined["parsed_phone"].notna().sum()
    print(f"Rows with valid 10-digit phone numbers: {valid_phones}")
    print(f"Rows without valid phone numbers: {len(df_combined) - valid_phones}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(analyze())
