"""
import_missing_calls.py
========================
Imports call_history records from the Futwork CSV that are missing from the DB.

Groups:
  Group A (2340): Repeat calls - same phone exists in DB but different callSid not stored
  Group B (676):  Truly new calls - phone never seen in DB; link to lead if found

For each missing callSid:
  1. Parse CSV row using the existing csv_processor utility (same mapping as webhook)
  2. Insert into call_history (skip if callSid already exists - idempotent)
  3. Link to lead via mobile_digits (update lead_id on call_history doc)

Does NOT overwrite existing call_history records.
Does NOT overwrite lead fields (transcript/disposition etc.) - only inserts new rows.
"""
import asyncio
import os
import sys
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv('.env')
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app.utils.csv_processor import process_call_report_row_to_call_history_and_lead_patches

CSV_DIR = r"c:\Users\Admin\Desktop\clara\Rustomjee_Dash-main\backend\csv"
MAIN_CSV1 = os.path.join(CSV_DIR, "rustomjee-lead-qualification-piya-2026-05-02-2026-05-08-ai_platform_call_history_report-230124c3-5000-431e-820d-e217b387b8fa.csv")
MAIN_CSV2 = os.path.join(CSV_DIR, "rustomjee-lead-qualification-piya-2026-05-27-2026-06-11-ai_platform_call_history_report-043ef4ab-7b44-4d48-85f5-5a0f5e7fc51a.csv")


async def run(dry_run: bool = False):
    client = AsyncIOMotorClient(os.getenv("MONGO_URL"))
    db = client["rustomjee_db"]

    print("=" * 70)
    print(f"  IMPORT MISSING CALL HISTORY FROM CSV {'(DRY RUN)' if dry_run else ''}")
    print("=" * 70)

    # Step 1: Get all existing callSids from DB
    print("Step 1: Loading existing call IDs from DB (both id + call_sid fields)...")
    db_call_set = set()   # stores values from `id` field
    db_sid_set = set()    # stores values from `call_sid` field
    async for c in db.call_history.find({}, {"id": 1, "call_sid": 1}):
        if c.get("id"):
            db_call_set.add(str(c["id"]))
        if c.get("call_sid"):
            db_sid_set.add(str(c["call_sid"]))
    print(f"  Found {len(db_call_set)} records by `id`, {len(db_sid_set)} by `call_sid` in DB.")

    # Step 2: Load CSVs
    print("Step 2: Loading CSV files...")
    df1 = pd.read_csv(MAIN_CSV1, low_memory=False)
    df2 = pd.read_csv(MAIN_CSV2, low_memory=False)
    df_combined = pd.concat([df1, df2], ignore_index=True)
    print(f"  Loaded {len(df_combined)} total rows from CSVs.")

    # Step 3: Find missing rows
    missing_rows = []
    already_in_db_by_sid = []  # callSid exists in `call_sid` field but not `id` field — just needs lead link
    for _, row in df_combined.iterrows():
        call_sid = str(row.get("callSid") or "").strip()
        if not call_sid:
            continue
        if call_sid in db_call_set:
            continue  # Already in DB by `id`
        if call_sid in db_sid_set:
            already_in_db_by_sid.append(row.to_dict())  # Exists by call_sid, just link lead
        else:
            missing_rows.append(row.to_dict())
    print(f"  Truly missing (not in DB at all): {len(missing_rows)}")
    print(f"  Exists by call_sid but needs lead link: {len(already_in_db_by_sid)}")

    print(f"  Found {len(missing_rows)} calls missing from DB.")

    if not missing_rows and not already_in_db_by_sid:
        print("Nothing to import or patch. Exiting.")
        client.close()
        return

    # Step 4: Build lead phone->id lookup cache
    print("Step 3: Building lead lookup cache (phone -> lead_id)...")
    phone_to_lead = {}
    async for lead in db.leads.find({}, {"id": 1, "mobile_digits": 1}):
        phone = lead.get("mobile_digits")
        if phone:
            phone_to_lead[str(phone)] = str(lead.get("id", ""))
    print(f"  Cached {len(phone_to_lead)} leads by phone.")

    # Step 5: Insert missing records
    print(f"Step 4: Inserting {len(missing_rows)} missing call records...")
    inserted = 0
    skipped = 0
    linked = 0
    no_lead = 0
    errors = 0

    for i, row in enumerate(missing_rows):
        if i % 200 == 0:
            print(f"  [Progress] {i}/{len(missing_rows)} ... (inserted={inserted}, linked={linked}, errors={errors})")

        try:
            call_set, lead_set, call_sid = process_call_report_row_to_call_history_and_lead_patches(row)

            if not call_sid:
                skipped += 1
                continue

            # Try to find the lead by phone
            mobile = call_set.get("mobile_digits", "")
            lead_id = phone_to_lead.get(mobile)

            if lead_id:
                call_set["lead_id"] = lead_id
                linked += 1
            else:
                no_lead += 1

            # Add created_at if not set
            if "created_at" not in call_set:
                call_set["created_at"] = datetime.now(timezone.utc)

            if not dry_run:
                result = await db.call_history.update_one(
                    {"id": call_sid},
                    {"$setOnInsert": call_set},
                    upsert=True
                )
                if result.upserted_id:
                    inserted += 1
                else:
                    skipped += 1
            else:
                inserted += 1

        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  ERROR on row {i}: {e}")

    # Step 5b: Patch lead_id on records that exist by call_sid but are missing lead link
    print(f"\nStep 5b: Patching lead_id on {len(already_in_db_by_sid)} records already in DB by call_sid...")
    patched = 0
    for row in already_in_db_by_sid:
        try:
            call_set, _, call_sid = process_call_report_row_to_call_history_and_lead_patches(row)
            if not call_sid:
                continue
            mobile = call_set.get("mobile_digits", "")
            lead_id = phone_to_lead.get(mobile)
            if lead_id and not dry_run:
                await db.call_history.update_one(
                    {"call_sid": call_sid, "lead_id": {"$in": [None, ""]}},
                    {"$set": {"lead_id": lead_id}}
                )
                patched += 1
            elif lead_id:
                patched += 1
        except Exception:
            pass
    print(f"  Patched lead_id on: {patched} existing records.")

    print(f"\n{'=' * 70}")
    print(f"  IMPORT COMPLETE")
    print(f"{'=' * 70}")
    print(f"  Inserted new call_history records : {inserted}")
    print(f"  Linked to existing lead           : {linked}")
    print(f"  No matching lead found            : {no_lead}")
    print(f"  Skipped (already existed)         : {skipped}")
    print(f"  Errors                            : {errors}")
    print(f"  Patched lead_id on existing docs  : {patched}")

    # Verify final count
    final_count = await db.call_history.count_documents({})
    print(f"\n  Final call_history count in DB    : {final_count}")

    client.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Preview without inserting")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))
