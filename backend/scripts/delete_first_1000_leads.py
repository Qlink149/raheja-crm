import asyncio
import os
import argparse
import pandas as pd
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.getenv("MONGO_URL", "")
DB_NAME   = os.getenv("DB_NAME", "rustomjee_db")
CSV_PATH  = r"c:\Users\Admin\Desktop\clara\Rustomjee_Dash-main\backend\csv\Sample Lead Dump 02-05-26- Rustomjee - Sheet1 (1) (1).csv"

async def run(dry_run: bool):
    print("Loading CSV...")
    try:
        df = pd.read_csv(CSV_PATH)
        print(f"Loaded {len(df)} rows.")
    except Exception as e:
        print(f"Failed to load CSV: {e}")
        return

    # Get the first 1000 rows
    df_1000 = df.head(1000)
    
    # Extract unique Lead Ids as strings
    if 'Lead Id' not in df_1000.columns:
        print(f"Column 'Lead Id' not found! Available columns: {df.columns.tolist()}")
        return

    lead_ids = [str(int(lid)) for lid in df_1000['Lead Id'].dropna().unique() if pd.notna(lid)]
    
    print(f"Extracted {len(lead_ids)} unique Lead Ids from the first 1000 rows.")
        
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    # Search for leads matching these IDs in `client_lead_id`
    query = {"client_lead_id": {"$in": lead_ids}}
    
    cursor = db.leads.find(query, {"id": 1, "client_lead_id": 1})
    leads_matched = await cursor.to_list(length=None)
    
    print("=" * 70)
    print(f"  DELETE FIRST 1000 LEADS SCRIPT (EXCLUDING CALLS) {'(DRY RUN)' if dry_run else ''}")
    print("=" * 70)
    print(f"Found {len(leads_matched)} leads in the database matching these client_lead_ids.")
    
    # Find corresponding internal IDs to check call_history
    internal_ids = [str(lead.get("id")) for lead in leads_matched if lead.get("id")]
    
    call_history_query = {"lead_id": {"$in": internal_ids}}
    cursor_calls = db.call_history.find(call_history_query, {"lead_id": 1})
    calls_matched = await cursor_calls.to_list(length=None)
    
    # Get distinct lead_ids that have calls
    lead_ids_with_calls = set([str(call.get("lead_id")) for call in calls_matched])
    
    print(f"Found {len(calls_matched)} call history records.")
    print(f"These calls belong to {len(lead_ids_with_calls)} distinct leads.")
    
    # Filter out leads that have calls
    leads_to_delete = [lead for lead in leads_matched if str(lead.get("id")) not in lead_ids_with_calls]
    
    print(f"Skipping {len(leads_matched) - len(leads_to_delete)} leads because they have call history.")
    print(f"Targeting {len(leads_to_delete)} leads for deletion.")

    if len(leads_to_delete) == 0:
        print("No leads to delete.")
        client.close()
        return

    ids_to_delete = [str(lead.get("id")) for lead in leads_to_delete]
    final_query = {"id": {"$in": ids_to_delete}}

    if dry_run:
        print(f"Dry run enabled. WOULD DELETE {len(ids_to_delete)} documents from `leads`.")
    else:
        result_leads = await db.leads.delete_many(final_query)
        print(f"Successfully deleted {result_leads.deleted_count} documents from the `leads` collection.")
        
    client.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delete first 1000 leads by Lead Id, excluding those with calls.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without making changes.")
    args = parser.parse_args()
    
    asyncio.run(run(dry_run=args.dry_run))
