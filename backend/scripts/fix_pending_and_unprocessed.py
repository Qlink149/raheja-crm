import asyncio
import os
import argparse
import pandas as pd
import uuid
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.getenv("MONGO_URL", "")
DB_NAME   = os.getenv("DB_NAME", "rustomjee_db")
CSV_DIR = r"c:\Users\Admin\Desktop\clara\Rustomjee_Dash-main\backend\csv"
MAIN_CSV1 = os.path.join(CSV_DIR, "rustomjee-lead-qualification-piya-2026-05-02-2026-05-08-ai_platform_call_history_report-230124c3-5000-431e-820d-e217b387b8fa.csv")
MAIN_CSV2 = os.path.join(CSV_DIR, "rustomjee-lead-qualification-piya-2026-05-27-2026-06-11-ai_platform_call_history_report-043ef4ab-7b44-4d48-85f5-5a0f5e7fc51a.csv")

def extract_mobile_digits(phone_str):
    if pd.isna(phone_str): return ""
    digits = ''.join([c for c in str(phone_str) if c.isdigit()])
    return digits[-10:] if len(digits) >= 10 else digits

async def run(dry_run: bool):
    print("Loading Main Processed CSVs...")
    df1 = pd.read_csv(MAIN_CSV1, low_memory=False)
    df2 = pd.read_csv(MAIN_CSV2, low_memory=False)
    
    # Combine dataframes for easy lookup
    df_combined = pd.concat([df1, df2], ignore_index=True)
    df_combined['mobile_digits'] = df_combined['contextDetails_recipientPhoneNumber'].apply(extract_mobile_digits)
    
    # Create dictionary mapping mobile_digits -> csv row dict
    csv_row_map = {}
    for _, row in df_combined.dropna(subset=['mobile_digits']).iterrows():
        m = row['mobile_digits']
        if m:
            csv_row_map[m] = row.to_dict()

    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    cursor = db.leads.find({"futwork_sync_status": "pending"})
    pending_leads = await cursor.to_list(length=None)
    
    unprocessed_group_ids = []
    dialed_group_updates = []
    call_history_inserts = []
    processed_mobile_digits = set()
    
    print("Building cache of successfully synced leads...")
    fields_to_copy = [
        "transcript", "call_summary", "ai_call_summary", "disposition", 
        "ai_disposition", "status", "qualification_category", 
        "budget_category", "location_category", "intent_category",
        "temperature", "call_duration", "recording_url", "mobile_digits", "ls"
    ]
    projection = {f: 1 for f in fields_to_copy}
    
    synced_cache = {}
    async for sl in db.leads.find({"transcript": {"$type": "string", "$ne": ""}}, projection):
        m = sl.get("mobile_digits")
        if m and m not in synced_cache:
            synced_cache[m] = sl
            
    print(f"Cached {len(synced_cache)} unique numbers with transcripts.")
    
    source_twin = 0
    source_csv = 0
    
    for lead in pending_leads:
        m = lead.get("mobile_digits", "")
        lead_id = lead.get("_id")
        lead_id_str = str(lead_id)
        
        if m not in csv_row_map:
            unprocessed_group_ids.append(lead_id)
        else:
            update_doc = {"futwork_sync_status": "pushed"}
            
            # 1. Map data directly onto the lead from a DB Twin
            twin = synced_cache.get(m)
            if twin:
                source_twin += 1
                for f in fields_to_copy:
                    if f != "mobile_digits" and twin.get(f) is not None:
                        update_doc[f] = twin.get(f)
                
                # NOTE: We do NOT duplicate call_history here!
                # The backend API endpoints fetch call_history using {"mobile_digits": mobile_digits}
                # So this pending lead will automatically show the twin's call history. No data inflation!
                    
            # 2. Or, if no Twin exists, extract data from CSV directly
            else:
                source_csv += 1
                row = csv_row_map[m]
                
                transcript = row.get("transcript")
                ai_call_summary = row.get("extractedData_call_summary")
                disposition = row.get("disposition")
                ai_disp = row.get("extractedData_disposition")
                
                if pd.notna(transcript): update_doc["transcript"] = str(transcript)
                if pd.notna(ai_call_summary): update_doc["ai_call_summary"] = str(ai_call_summary)
                if pd.notna(disposition): update_doc["disposition"] = str(disposition)
                if pd.notna(ai_disp): update_doc["ai_disposition"] = str(ai_disp)
                
                # Check if call_history actually exists for this mobile digit
                # if not, we create ONE record, and it will apply to all duplicates!
                if m not in processed_mobile_digits:
                    processed_mobile_digits.add(m)
                    existing_call = await db.call_history.find_one({"mobile_digits": m})
                    if not existing_call:
                        new_call = {
                            "id": uuid.uuid4().hex,
                            "lead_id": lead_id_str, # Primary mapping (fallback API uses mobile_digits anyway)
                            "call_sid": str(row.get('callSid')) if pd.notna(row.get('callSid')) else uuid.uuid4().hex,
                            "agent_id": str(row.get("agentId")) if pd.notna(row.get("agentId")) else None,
                            "campaign_id": str(row.get("contextDetails_recipientData_campaignId")) if pd.notna(row.get("contextDetails_recipientData_campaignId")) else None,
                            "created_at": str(row.get("createdAt")) if pd.notna(row.get("createdAt")) else None,
                            "customer_name": str(row.get("contextDetails_recipientData_customer_name")) if pd.notna(row.get("contextDetails_recipientData_customer_name")) else None,
                            "from_number": str(row.get("telephonyData_fromNumber")) if pd.notna(row.get("telephonyData_fromNumber")) else None,
                            "to_number": str(row.get("telephonyData_toNumber")) if pd.notna(row.get("telephonyData_toNumber")) else None,
                            "mobile_digits": m,
                            "status": str(row.get("status")) if pd.notna(row.get("status")) else None,
                            "duration": int(row.get("duration", 0)) if pd.notna(row.get("duration")) else 0,
                            "recording_url": str(row.get("recordingUrl")) if pd.notna(row.get("recordingUrl")) else None,
                            "disposition": str(disposition) if pd.notna(disposition) else None,
                            "transcript": str(transcript) if pd.notna(transcript) else None,
                            "ai_disposition": str(ai_disp) if pd.notna(ai_disp) else None
                        }
                        call_history_inserts.append(new_call)
            
            dialed_group_updates.append({
                "id": lead_id,
                "update": update_doc
            })
            
    print("=" * 70)
    print(f"  FIX PENDING LEADS SCRIPT {'(DRY RUN)' if dry_run else ''}")
    print("=" * 70)
    print(f"Total pending leads found: {len(pending_leads)}")
    print(f"Group 1 (Unprocessed/Invalid): {len(unprocessed_group_ids)} leads")
    print(f"Group 2 (Dialed but still pending): {len(dialed_group_updates)} leads")
    print(f"  -> Extracted data from DB Twin: {source_twin} leads")
    print(f"  -> Extracted data from CSV Raw: {source_csv} leads")
    print(f"  -> Unique call_history insertions required: {len(call_history_inserts)}")
    
    if dry_run:
        print("\n[DRY RUN] Finished computing. No changes made.")
    else:
        # Update Group 1
        if unprocessed_group_ids:
            res1 = await db.leads.update_many(
                {"_id": {"$in": unprocessed_group_ids}},
                {"$set": {
                    "futwork_sync_status": "pushed",
                    "status": "Invalid Number",
                    "ai_call_summary": "Number was invalid or rejected before dialing"
                }}
            )
            print(f"Successfully updated {res1.modified_count} leads in Group 1.")
            
        # Update Group 2 Leads
        success_count = 0
        for upd in dialed_group_updates:
            res2 = await db.leads.update_one(
                {"_id": upd["id"]},
                {"$set": upd["update"]}
            )
            success_count += res2.modified_count
            
        print(f"Successfully updated {success_count} leads in Group 2.")
        
        # Insert Call History
        if call_history_inserts:
            try:
                res3 = await db.call_history.insert_many(call_history_inserts, ordered=False)
                print(f"Successfully inserted {len(res3.inserted_ids)} call_history records.")
            except Exception as e:
                print(f"Inserted call history with some bypassable errors: {e}")
            
    client.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fix pending leads.")
    parser.add_argument("--dry-run", action="store_true", help="Dry run")
    args = parser.parse_args()
    
    asyncio.run(run(dry_run=args.dry_run))
