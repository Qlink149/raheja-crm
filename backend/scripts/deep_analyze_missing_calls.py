import asyncio
import os
import pandas as pd
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv('.env')

CSV_DIR = r"c:\Users\Admin\Desktop\clara\Rustomjee_Dash-main\backend\csv"
MAIN_CSV1 = os.path.join(CSV_DIR, "rustomjee-lead-qualification-piya-2026-05-02-2026-05-08-ai_platform_call_history_report-230124c3-5000-431e-820d-e217b387b8fa.csv")
MAIN_CSV2 = os.path.join(CSV_DIR, "rustomjee-lead-qualification-piya-2026-05-27-2026-06-11-ai_platform_call_history_report-043ef4ab-7b44-4d48-85f5-5a0f5e7fc51a.csv")

async def deep_analyze():
    client = AsyncIOMotorClient(os.getenv("MONGO_URL"))
    db = client["rustomjee_db"]

    print("Loading DB call IDs...")
    db_call_set = set()
    async for c in db.call_history.find({}, {"id": 1}):
        if c.get("id"):
            db_call_set.add(str(c["id"]))
    print(f"Loaded {len(db_call_set)} call IDs from DB.")

    print("Loading CSVs...")
    df1 = pd.read_csv(MAIN_CSV1, low_memory=False)
    df2 = pd.read_csv(MAIN_CSV2, low_memory=False)
    df_combined = pd.concat([df1, df2], ignore_index=True)

    # Separate missing vs present rows
    missing_rows = []
    for _, row in df_combined.iterrows():
        if str(row.get("callSid")) not in db_call_set:
            missing_rows.append(row)

    missing_df = pd.DataFrame(missing_rows)
    print(f"\n{'='*60}")
    print(f"TOTAL MISSING: {len(missing_df)} calls")
    print(f"{'='*60}")

    # Q1: Are these calls to phone numbers that DO exist in DB, just different calls?
    # i.e., DB has ONE call for that phone but CSV has multiple calls
    def extract_phone(row):
        num = str(row.get("contextDetails_recipientPhoneNumber"))
        if num == "nan":
            num = str(row.get("telephonyData_toNumber"))
        digits = "".join([c for c in str(num) if c.isdigit()])
        if len(digits) > 10 and digits.startswith("91"):
            digits = digits[2:]
        return digits if len(digits) == 10 else None

    missing_df["parsed_phone"] = missing_df.apply(extract_phone, axis=1)

    # Get all phones that already exist in DB call_history
    db_phones = set()
    async for c in db.call_history.find({}, {"mobile_digits": 1}):
        if c.get("mobile_digits"):
            db_phones.add(str(c["mobile_digits"]))
    print(f"Unique phones with calls already in DB: {len(db_phones)}")

    missing_phones_in_db = missing_df[missing_df["parsed_phone"].isin(db_phones)]
    missing_phones_new   = missing_df[~missing_df["parsed_phone"].isin(db_phones)]

    print(f"\n--- Group A: Missing calls where phone ALREADY EXISTS in DB call_history ---")
    print(f"  Count: {len(missing_phones_in_db)}")
    print(f"  (These are REPEAT CALLS to the same lead — DB has 1 entry, CSV has multiple)")
    if len(missing_phones_in_db) > 0:
        print(f"  Status breakdown:")
        print(missing_phones_in_db["status"].value_counts().to_string())

    print(f"\n--- Group B: Missing calls where phone DOES NOT exist in DB call_history ---")
    print(f"  Count: {len(missing_phones_new)}")
    print(f"  (These are truly brand-new calls never seen in DB at all)")
    if len(missing_phones_new) > 0:
        print(f"  Status breakdown:")
        print(missing_phones_new["status"].value_counts().to_string())

    # Q2: For Group B — do we at least have these leads in the leads collection?
    if len(missing_phones_new) > 0:
        new_phones = missing_phones_new["parsed_phone"].dropna().unique().tolist()
        in_leads_count = await db.leads.count_documents({"mobile_digits": {"$in": new_phones}})
        print(f"\n  Of those {len(new_phones)} unique new phones, {in_leads_count} exist in leads collection.")

    client.close()

if __name__ == "__main__":
    asyncio.run(deep_analyze())
