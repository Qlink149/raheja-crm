import asyncio
import os
import glob
import pandas as pd
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.getenv("MONGO_URL", "")
DB_NAME   = os.getenv("DB_NAME", "rustomjee_db")

CSV_DIR = r"c:\Users\Admin\Desktop\clara\Rustomjee_Dash-main\backend\csv"
UNPROCESSED_DIR = os.path.join(CSV_DIR, "unprocessed")

MAIN_CSV1 = os.path.join(CSV_DIR, "rustomjee-lead-qualification-piya-2026-05-02-2026-05-08-ai_platform_call_history_report-230124c3-5000-431e-820d-e217b387b8fa.csv")
MAIN_CSV2 = os.path.join(CSV_DIR, "rustomjee-lead-qualification-piya-2026-05-27-2026-06-11-ai_platform_call_history_report-043ef4ab-7b44-4d48-85f5-5a0f5e7fc51a.csv")

def extract_mobile_digits(phone_str):
    if pd.isna(phone_str): return ""
    digits = ''.join([c for c in str(phone_str) if c.isdigit()])
    return digits[-10:] if len(digits) >= 10 else digits

async def run():
    print("Loading Main Processed CSVs...")
    df1 = pd.read_csv(MAIN_CSV1, low_memory=False)
    df2 = pd.read_csv(MAIN_CSV2, low_memory=False)
    
    csv1_mobiles = set(df1['contextDetails_recipientPhoneNumber'].apply(extract_mobile_digits).dropna().unique())
    csv2_mobiles = set(df2['contextDetails_recipientPhoneNumber'].apply(extract_mobile_digits).dropna().unique())
    main_csv_mobiles = csv1_mobiles.union(csv2_mobiles)
    main_csv_mobiles.discard("")
    
    print(f"Total unique mobiles in main processed CSVs: {len(main_csv_mobiles)}")

    print("\nLoading Unprocessed CSVs...")
    unprocessed_files = glob.glob(os.path.join(UNPROCESSED_DIR, "*.csv"))
    unprocessed_mobiles = set()
    total_unprocessed_rows = 0
    
    for f in unprocessed_files:
        try:
            df = pd.read_csv(f)
            total_unprocessed_rows += len(df)
            if 'recipientPhoneNumber' in df.columns:
                mobiles = set(df['recipientPhoneNumber'].apply(extract_mobile_digits).dropna().unique())
                unprocessed_mobiles = unprocessed_mobiles.union(mobiles)
        except Exception as e:
            print(f"Error loading {f}: {e}")
            
    unprocessed_mobiles.discard("")
    print(f"Loaded {len(unprocessed_files)} unprocessed CSV files.")
    print(f"Total rows in unprocessed CSVs: {total_unprocessed_rows}")
    print(f"Total unique mobiles in unprocessed CSVs: {len(unprocessed_mobiles)}")

    print("\nConnecting to Database...")
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    cursor = db.leads.find({}, {"mobile_digits": 1, "id": 1, "source": 1})
    db_leads = await cursor.to_list(length=None)
    db_mobiles = set(lead.get("mobile_digits") for lead in db_leads if lead.get("mobile_digits"))
    db_mobiles.discard("")
    
    print(f"Total leads in DB: {len(db_leads)}")
    print(f"Unique mobile numbers in leads collection: {len(db_mobiles)}")
    
    # The 1,357 calculation
    in_db_but_not_main_csv = db_mobiles - main_csv_mobiles
    print(f"\nLeads in DB but NOT in Main CSVs (The '1,357' pending group): {len(in_db_but_not_main_csv)}")
    
    # Compare with Unprocessed
    unprocessed_in_db = unprocessed_mobiles.intersection(db_mobiles)
    unprocessed_in_pending_group = unprocessed_mobiles.intersection(in_db_but_not_main_csv)
    
    print(f"\n--- Analysis of Unprocessed Mobiles ---")
    print(f"Unprocessed mobiles found anywhere in DB: {len(unprocessed_in_db)} / {len(unprocessed_mobiles)}")
    print(f"Unprocessed mobiles specifically in the 'Pending' group: {len(unprocessed_in_pending_group)} / {len(in_db_but_not_main_csv)}")
    
    # Is there a gap?
    unexplained_pending = in_db_but_not_main_csv - unprocessed_mobiles
    print(f"Pending leads NOT explained by unprocessed CSVs: {len(unexplained_pending)}")
    
    if len(unexplained_pending) > 0:
        print(f"Sample unexplained pending numbers: {list(unexplained_pending)[:5]}")

    client.close()

if __name__ == "__main__":
    asyncio.run(run())
