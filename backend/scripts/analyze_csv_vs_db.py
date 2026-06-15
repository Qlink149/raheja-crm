import asyncio
import os
import sys
import pandas as pd
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.getenv("MONGO_URL", "")
DB_NAME   = os.getenv("DB_NAME", "rustomjee_db")

CSV1 = r"c:\Users\Admin\Desktop\clara\Rustomjee_Dash-main\backend\csv\rustomjee-lead-qualification-piya-2026-05-02-2026-05-08-ai_platform_call_history_report-230124c3-5000-431e-820d-e217b387b8fa.csv"
CSV2 = r"c:\Users\Admin\Desktop\clara\Rustomjee_Dash-main\backend\csv\rustomjee-lead-qualification-piya-2026-05-27-2026-06-11-ai_platform_call_history_report-043ef4ab-7b44-4d48-85f5-5a0f5e7fc51a.csv"

def extract_mobile_digits(phone_str):
    if pd.isna(phone_str): return ""
    digits = ''.join([c for c in str(phone_str) if c.isdigit()])
    return digits[-10:] if len(digits) >= 10 else digits

async def run():
    print("Loading CSVs...")
    try:
        df1 = pd.read_csv(CSV1, low_memory=False)
        print(f"CSV1 (Old): Loaded {len(df1)} rows")
    except Exception as e:
        print(f"Error loading CSV1: {e}")
        df1 = pd.DataFrame()

    try:
        df2 = pd.read_csv(CSV2, low_memory=False)
        print(f"CSV2 (New): Loaded {len(df2)} rows")
    except Exception as e:
        print(f"Error loading CSV2: {e}")
        df2 = pd.DataFrame()

    # The actual customer phone is in contextDetails_recipientPhoneNumber or telephonyData_toNumber
    phone_col_1 = 'contextDetails_recipientPhoneNumber' if 'contextDetails_recipientPhoneNumber' in df1.columns else 'telephonyData_toNumber'
    phone_col_2 = 'contextDetails_recipientPhoneNumber' if 'contextDetails_recipientPhoneNumber' in df2.columns else 'telephonyData_toNumber'
    
    csv1_mobiles = set()
    if phone_col_1 in df1.columns:
        csv1_mobiles = set(df1[phone_col_1].apply(extract_mobile_digits).dropna().unique())
        csv1_mobiles.discard("")
        print(f"CSV1 (Old): {len(csv1_mobiles)} unique mobile numbers based on column '{phone_col_1}'.")
    else:
        print(f"CSV1 missing phone columns!")

    csv2_mobiles = set()
    if phone_col_2 in df2.columns:
        csv2_mobiles = set(df2[phone_col_2].apply(extract_mobile_digits).dropna().unique())
        csv2_mobiles.discard("")
        print(f"CSV2 (New): {len(csv2_mobiles)} unique mobile numbers based on column '{phone_col_2}'.")
    else:
        print(f"CSV2 missing phone columns!")
        
    combined_csv_mobiles = csv1_mobiles.union(csv2_mobiles)
    print(f"Total unique mobiles across both CSVs: {len(combined_csv_mobiles)}")

    print("\nConnecting to Database...")
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    total_leads = await db.leads.count_documents({})
    print(f"Total leads in DB: {total_leads}")
    
    cursor = db.leads.find({}, {"mobile_digits": 1, "id": 1, "source": 1})
    db_leads = await cursor.to_list(length=None)
    db_mobiles = set(lead.get("mobile_digits") for lead in db_leads if lead.get("mobile_digits"))
    print(f"Unique mobile numbers in leads collection: {len(db_mobiles)}")
    
    total_calls = await db.call_history.count_documents({})
    cursor = db.call_history.find({}, {"mobile_digits": 1, "call_sid": 1, "lead_id": 1})
    db_calls = await cursor.to_list(length=None)
    db_call_mobiles = set(call.get("mobile_digits") for call in db_calls if call.get("mobile_digits"))
    
    print(f"Total calls in call_history DB: {total_calls}")
    print(f"Unique mobile numbers in call_history collection: {len(db_call_mobiles)}")
    
    print("\n--- Overlap Analysis ---")
    in_db_but_not_csv = db_mobiles - combined_csv_mobiles
    in_csv_but_not_db = combined_csv_mobiles - db_mobiles
    print(f"Leads in DB but NOT in CSVs: {len(in_db_but_not_csv)}")
    print(f"Leads in CSVs but NOT in DB: {len(in_csv_but_not_db)}")
    
    # Check duplicate mobile numbers in leads collection
    mobile_counts = {}
    for lead in db_leads:
        m = lead.get("mobile_digits")
        if m:
            mobile_counts[m] = mobile_counts.get(m, 0) + 1
            
    duplicates = {m: c for m, c in mobile_counts.items() if c > 1}
    print(f"\n--- Duplicates Analysis ---")
    print(f"Number of mobile numbers that appear MULTIPLE times in leads collection: {len(duplicates)}")
    if duplicates:
        # Sort and print top 10
        sorted_dups = sorted(duplicates.items(), key=lambda item: item[1], reverse=True)
        print(f"Top 10 duplicated numbers: {sorted_dups[:10]}")
        
    # How many of the CSV mobiles are in call_history?
    csv_mobiles_in_calls = combined_csv_mobiles.intersection(db_call_mobiles)
    print(f"CSV Mobiles present in call_history: {len(csv_mobiles_in_calls)} / {len(combined_csv_mobiles)}")

    client.close()

if __name__ == "__main__":
    asyncio.run(run())
