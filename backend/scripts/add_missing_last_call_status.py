import asyncio
import os
import pandas as pd
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv('.env')

CSV_DIR = r"c:\Users\Admin\Desktop\clara\Rustomjee_Dash-main\backend\csv"
MAIN_CSV1 = os.path.join(CSV_DIR, "rustomjee-lead-qualification-piya-2026-05-02-2026-05-08-ai_platform_call_history_report-230124c3-5000-431e-820d-e217b387b8fa.csv")
MAIN_CSV2 = os.path.join(CSV_DIR, "rustomjee-lead-qualification-piya-2026-05-27-2026-06-11-ai_platform_call_history_report-043ef4ab-7b44-4d48-85f5-5a0f5e7fc51a.csv")

async def run():
    client = AsyncIOMotorClient(os.getenv("MONGO_URL"))
    db = client["rustomjee_db"]
    
    print("Loading CSVs...")
    df1 = pd.read_csv(MAIN_CSV1, low_memory=False)
    df2 = pd.read_csv(MAIN_CSV2, low_memory=False)
    
    csv_row_map = {}
    for df in [df1, df2]:
        for _, row in df.iterrows():
            # Phone number parsing
            num = str(row.get("contextDetails_recipientPhoneNumber"))
            if pd.isna(num) or num == "nan":
                num = str(row.get("telephonyData_toNumber"))
            if pd.isna(num) or num == "nan":
                continue
                
            digits = "".join([c for c in str(num) if c.isdigit()])
            if len(digits) > 10 and digits.startswith("91"):
                digits = digits[2:]
            if len(digits) == 10:
                csv_row_map[digits] = row.to_dict()
                
    print(f"Loaded {len(csv_row_map)} unique phones from CSVs.")
    
    # Find all leads missing last_call_status but with transcripts
    cursor = db.leads.find({
        "transcript": {"$type": "string", "$ne": ""},
        "$or": [
            {"last_call_status": {"$in": ["", None]}},
            {"last_call_status": {"$exists": False}}
        ]
    })
    
    leads_to_update = await cursor.to_list(length=None)
    print(f"Found {len(leads_to_update)} leads in DB missing last_call_status with transcripts.")
    
    updated_count = 0
    not_in_csv = 0
    
    for lead in leads_to_update:
        mobile = lead.get("mobile_digits")
        if not mobile or mobile not in csv_row_map:
            not_in_csv += 1
            continue
            
        row = csv_row_map[mobile]
        
        status = row.get("status")
        created_at = row.get("createdAt")
        duration = row.get("duration")
        recording_url = row.get("recordingUrl")
        
        update_doc = {}
        if pd.notna(status):
            update_doc["last_call_status"] = str(status)
            update_doc["last_call_status_raw"] = str(status)
        if pd.notna(created_at):
            update_doc["last_call_date"] = str(created_at)
        if pd.notna(duration):
            try:
                update_doc["last_call_duration"] = int(duration)
            except:
                pass
        if pd.notna(recording_url):
            update_doc["last_recording_url"] = str(recording_url)
            
        if update_doc:
            await db.leads.update_one({"_id": lead["_id"]}, {"$set": update_doc})
            updated_count += 1
            
    print(f"Successfully updated {updated_count} leads with CSV metadata.")
    print(f"Leads not found in CSV map: {not_in_csv}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(run())
