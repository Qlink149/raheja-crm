"""
Seed Script: seed_call_history.py
==================================
Imports `unmasked_call_report_completed.csv` into MongoDB.
Populates TWO collections:
  1. `call_history`  — one document per CSV row (upserted by _id / callSid)
  2. `leads`         — one document per unique phone number (upserted by mobile_digits)

Usage (from the /backend directory):
    python seed_call_history.py

Requirements:
    pip install motor pandas python-dotenv
"""

import asyncio
import hashlib
import os
import re
import sys
import uuid
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(SCRIPT_DIR, "unmasked_call_report_completed.csv")

load_dotenv(os.path.join(SCRIPT_DIR, ".env"))
MONGO_URI = os.getenv("MONGODB_URL") or os.getenv("MONGO_URL") or os.getenv("DATABASE_URL")
DB_NAME   = os.getenv("DATABASE_NAME", "rustomjee_db")

BATCH_SIZE = 200          # rows per bulk-write batch
FUTWORK_CAMPAIGN_ID = os.getenv("FUTWORK_CAMPAIGN_ID", "")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_phone(raw) -> str:
    """Strip non-digits and return the last 10 digits."""
    if raw is None or (isinstance(raw, float) and raw != raw):
        return ""
    digits = re.sub(r"\D", "", str(raw))
    return digits[-10:] if len(digits) >= 10 else digits


def safe_str(val) -> str:
    if val is None or (isinstance(val, float) and val != val):
        return ""
    return str(val).strip()


def safe_int(val, default=0) -> int:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default


def parse_dt(val):
    """Parse ISO datetime string to Python datetime, or return None."""
    s = safe_str(val)
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:26], fmt[:len(fmt)])
        except ValueError:
            pass
    return None


def get_temperature(disposition: str, status: str) -> str:
    """Derive lead temperature from disposition / call status."""
    d = disposition.lower()
    if d in ("interested", "highly interested", "hot", "callback", "qualified"):
        return "Hot"
    if d in ("partially interested", "callback requested", "busy"):
        return "Warm"
    if d in ("not interested", "dnc", "dropped"):
        return "Cold"
    # fallback by status
    if status == "completed":
        return "Warm"
    return "Cold"


def get_seed_key(mobile_digits: str) -> str:
    """Deterministic key for lead dedup — phone number only."""
    return hashlib.sha256(mobile_digits.encode()).hexdigest()


def map_disposition(raw_disp: str, status: str) -> str:
    """Clean disposition label."""
    d = safe_str(raw_disp)
    if d:
        return d
    # derive from status
    status_map = {
        "completed":  "Completed",
        "no-answer":  "No Answer",
        "busy":       "Busy",
        "failed":     "Failed",
    }
    return status_map.get(status, "")


# ---------------------------------------------------------------------------
# Main seed logic
# ---------------------------------------------------------------------------

async def seed():
    if not MONGO_URI:
        print("[ERR] No MONGODB_URL found in .env -- aborting.")
        sys.exit(1)

    print(f"[CSV] Reading: {CSV_PATH}")
    try:
        df = pd.read_csv(CSV_PATH, dtype=str, keep_default_na=False)
    except FileNotFoundError:
        print(f"❌  File not found: {CSV_PATH}")
        sys.exit(1)

    total_rows = len(df)
    print(f"[OK] Loaded {total_rows:,} rows. Columns: {list(df.columns)[:8]} ...")

    client = AsyncIOMotorClient(MONGO_URI)
    db     = client[DB_NAME]

    call_history_col = db.call_history
    leads_col        = db.leads

    # Ensure indexes (ignore conflicts if already exist with different options)
    for coro in [
        call_history_col.create_index("call_sid", unique=True, sparse=True),
        call_history_col.create_index("mobile_digits"),
        leads_col.create_index("mobile_digits"),
        leads_col.create_index("_seed_key"),
    ]:
        try:
            await coro
        except Exception:
            pass
    print("[DB] Indexes ensured.")

    call_history_ops = []
    leads_ops        = []

    call_upserted = call_skipped = call_errors = 0
    lead_upserted = lead_new = lead_errors = 0

    from pymongo import UpdateOne

    for idx, row in df.iterrows():
        # ---------------------------------------------------------------
        # 1. Extract & clean fields
        # ---------------------------------------------------------------
        futwork_id      = safe_str(row.get("_id"))          # Futwork's MongoDB _id
        call_sid        = safe_str(row.get("callSid"))
        agent_id        = safe_str(row.get("agentId"))
        status_raw      = safe_str(row.get("status")).lower()
        disposition_raw = safe_str(row.get("disposition"))
        minutes         = safe_int(row.get("minutes"))
        duration        = safe_int(row.get("duration"))
        recording_url   = safe_str(row.get("recordingUrl"))
        transcript      = safe_str(row.get("transcript"))
        dropoff         = safe_str(row.get("dropoff"))

        # Extracted data (AI summaries)
        call_summary    = safe_str(row.get("extractedData_call_summary"))
        callback_dt     = safe_str(row.get("extractedData_callback_date_time"))
        ext_disposition = safe_str(row.get("extractedData_disposition"))

        # Telephony
        direction       = safe_str(row.get("telephonyData_direction", "outbound"))
        from_number     = safe_str(row.get("telephonyData_fromNumber"))
        provider        = safe_str(row.get("telephonyData_provider"))
        hangup_by       = safe_str(row.get("telephonyData_hangupBy"))

        # Context / recipient
        ctx_campaign_id = safe_str(row.get("contextDetails_recipientData_campaignId"))
        customer_name   = safe_str(row.get("contextDetails_recipientData_customer_name"))
        lead_id_futwork = safe_str(row.get("contextDetails_recipientData_leadId"))
        unique_id       = safe_str(row.get("contextDetails_recipientData_unique_identifier"))

        # 🔑  ALWAYS use the unmasked number
        unmasked_raw    = row.get("Unmasked_Mobile_Number") or row.get("contextDetails_recipientPhoneNumber", "")
        mobile_digits   = normalize_phone(unmasked_raw)

        if not mobile_digits:
            call_skipped += 1
            continue

        mobile_full = "+91" + mobile_digits if len(mobile_digits) == 10 else mobile_digits

        # Timestamps
        created_at  = parse_dt(row.get("createdAt"))  or datetime.utcnow()
        updated_at  = parse_dt(row.get("updatedAt"))  or datetime.utcnow()
        uploaded_on = parse_dt(row.get("leadUploadedOn"))

        disposition = map_disposition(disposition_raw, status_raw)
        # Normalize status
        status_map = {
            "no-answer": "no-answer", "no_answer": "no-answer",
            "busy": "busy", "failed": "failed", "completed": "completed",
        }
        status = status_map.get(status_raw, status_raw)

        # ---------------------------------------------------------------
        # 2. call_history document
        # ---------------------------------------------------------------
        call_doc = {
            "call_sid":        call_sid or futwork_id,
            "futwork_call_id": futwork_id,
            "mobile_digits":   mobile_digits,
            "mobile":          mobile_full,
            "status":          status,
            "disposition":     disposition,
            "duration":        duration,
            "minutes":         minutes,
            "recording_url":   recording_url,
            "transcript":      transcript,
            "dropoff":         dropoff,
            "direction":       direction,
            "from_number":     from_number,
            "provider":        provider,
            "hangup_by":       hangup_by,
            "agent_id":        agent_id,
            "campaign_id":     ctx_campaign_id or FUTWORK_CAMPAIGN_ID,
            "customer_name":   customer_name if customer_name not in ("-", "Unknown", "") else "",
            "lead_id_futwork": lead_id_futwork,
            "unique_id":       unique_id,
            "extracted_data":  {
                "call_summary":          call_summary,
                "callback_date_time":    callback_dt,
                "disposition":           ext_disposition,
            },
            "started_at":      created_at,
            "ended_at":        updated_at,
            "created_at":      created_at,
            "updated_at":      updated_at,
            "source":          "csv_seed",
        }

        # Upsert key: prefer callSid, fallback to futwork _id
        upsert_key = {"call_sid": call_doc["call_sid"]} if call_doc["call_sid"] else {"futwork_call_id": futwork_id}

        call_history_ops.append(
            UpdateOne(
                upsert_key,
                {
                    "$set": call_doc,
                    "$setOnInsert": {
                        "id":           str(uuid.uuid4()),
                        "_inserted_at": datetime.utcnow(),
                    },
                },
                upsert=True,
            )
        )

        # ---------------------------------------------------------------
        # 3. leads document (upsert by mobile_digits)
        # ---------------------------------------------------------------
        seed_key      = get_seed_key(mobile_digits)
        temperature   = get_temperature(disposition, status)
        clean_name    = customer_name if customer_name not in ("-", "Unknown", "", ".", "no last name") else "Unknown"

        lead_set_fields = {
            "mobile":          mobile_full,
            "mobile_digits":   mobile_digits,
            "updated_at":      updated_at,
            "source":          "Futwork CSV Import",
            "futwork_sync_status": "pushed",      # Already called by Futwork
            "campaign_id":     ctx_campaign_id or FUTWORK_CAMPAIGN_ID,
            "futwork_lead_id": lead_id_futwork,
        }

        # Always set full_name — fallback to "Unknown" if no real name
        lead_set_fields["full_name"]  = clean_name  # already "Unknown" if blank
        lead_set_fields["first_name"] = clean_name.split()[0] if clean_name != "Unknown" else "Unknown"

        # Only update disposition if completed call has one
        if disposition and status == "completed":
            lead_set_fields["disposition"] = disposition
            lead_set_fields["temperature"] = temperature
            # Update AI summary if available
            if call_summary:
                lead_set_fields["ai_call_summary"] = call_summary

        leads_ops.append(
            UpdateOne(
                {"mobile_digits": mobile_digits},
                {
                    "$set": lead_set_fields,
                    "$setOnInsert": {
                        "id":           str(uuid.uuid4()),
                        "_seed_key":    seed_key,
                        "created_at":   created_at,
                        "is_vip":       False,
                        "is_hni":       False,
                        "vip_category": "",
                    },
                },
                upsert=True,
            )
        )

        # ---------------------------------------------------------------
        # 4. Flush batches
        # ---------------------------------------------------------------
        if len(call_history_ops) >= BATCH_SIZE:
            try:
                res = await call_history_col.bulk_write(call_history_ops, ordered=False)
                call_upserted += res.upserted_count + res.modified_count
            except Exception as e:
                # Count what succeeded despite errors
                if hasattr(e, 'details'):
                    call_upserted += e.details.get('nUpserted', 0) + e.details.get('nModified', 0)
            call_history_ops = []

        if len(leads_ops) >= BATCH_SIZE:
            try:
                res = await leads_col.bulk_write(leads_ops, ordered=False)
                lead_upserted += res.upserted_count
                lead_new      += res.upserted_count
            except Exception as e:
                if hasattr(e, 'details'):
                    lead_upserted += e.details.get('nUpserted', 0)
            leads_ops = []

        if (int(idx) + 1) % 1000 == 0:
            print(f"  -> Processed {int(idx) + 1:,} / {total_rows:,} rows ...")

    # Flush remainders
    if call_history_ops:
        try:
            res = await call_history_col.bulk_write(call_history_ops, ordered=False)
            call_upserted += res.upserted_count + res.modified_count
        except Exception as e:
            if hasattr(e, 'details'):
                call_upserted += e.details.get('nUpserted', 0) + e.details.get('nModified', 0)

    if leads_ops:
        try:
            res = await leads_col.bulk_write(leads_ops, ordered=False)
            lead_upserted += res.upserted_count
            lead_new      += res.upserted_count
        except Exception as e:
            if hasattr(e, 'details'):
                lead_upserted += e.details.get('nUpserted', 0)

    print("\n" + "=" * 55)
    print("SEED COMPLETE")
    print(f"   call_history  -> {call_upserted:,} upserted  |  {call_skipped:,} skipped (no phone)")
    print(f"   leads         -> {lead_upserted:,} upserted (new Virtual Customers)")
    print("=" * 55)

    client.close()


if __name__ == "__main__":
    asyncio.run(seed())
