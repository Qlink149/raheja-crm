"""
One-time ingest of Futwork historical call report CSV into MongoDB.

Reads backend/unmasked_call_report_completed.csv — NOT used by production upload.

Usage (from backend/):
  python scripts/seed_historical_futwork.py --dry-run
  python scripts/seed_historical_futwork.py --dry-run --assign
  python scripts/seed_historical_futwork.py
  python scripts/seed_historical_futwork.py --assign --limit 100
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.csv_processor import (  # noqa: E402
    normalize_phone,
    process_call_report_row_to_call_history_and_lead_patches,
)
from app.services.assignment_service import AssignmentService  # noqa: E402

load_dotenv()

DEFAULT_CSV = Path(__file__).resolve().parents[1] / "unmasked_call_report_completed.csv"
BATCH_NAME = "Historical Futwork Import"


def _is_unassigned(lead_doc: dict) -> bool:
    uid = lead_doc.get("assigned_user_id")
    return uid is None or str(uid).strip() == ""


def _parse_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Map Futwork call-report columns (script-only; production upload unchanged)."""
    call_history_set, lead_set, call_sid = (
        process_call_report_row_to_call_history_and_lead_patches(row)
    )
    customer_name = str(
        row.get("contextDetails_recipientData_customer_name") or ""
    ).strip()
    if customer_name and customer_name != "-":
        call_history_set["customer_name"] = customer_name
    return {
        "call_history_set": call_history_set,
        "lead_set": lead_set,
        "call_sid": call_sid,
    }


async def seed(
    db,
    *,
    csv_path: Path,
    upload_batch_id: str,
    batch_name: str,
    dry_run: bool = False,
    limit: Optional[int] = None,
    auto_assign: bool = False,
) -> Dict[str, int]:
    stats = {
        "rows": 0,
        "calls_upserted": 0,
        "leads_created": 0,
        "leads_updated": 0,
        "failed": 0,
        "assigned": 0,
        "assign_candidates": 0,
        "assign_skipped_already_assigned": 0,
        "would_assign": 0,
        "leads_would_create": 0,
        "leads_would_update": 0,
    }
    new_lead_ids: List[str] = []
    unassigned_lead_ids: List[str] = []
    new_assign_mobiles: set[str] = set()

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            if limit is not None and idx >= limit:
                break
            stats["rows"] += 1
            try:
                parsed = _parse_row(row)
            except Exception:
                stats["failed"] += 1
                continue

            call_sid = parsed["call_sid"]
            ch_set = dict(parsed["call_history_set"] or {})
            created_at_val = ch_set.pop("created_at", None) or datetime.utcnow()
            lead_set = dict(parsed["lead_set"] or {})
            mobile_digits = str(lead_set.get("mobile_digits") or "").strip()

            if not call_sid or not mobile_digits:
                stats["failed"] += 1
                continue

            ch_set["upload_batch_id"] = upload_batch_id
            ch_set["upload_batch_name"] = batch_name
            ch_set["lead_id"] = ch_set.get("lead_id") or lead_set.get("futwork_lead_id") or ""

            if dry_run:
                stats["calls_upserted"] += 1
            else:
                await db.call_history.update_one(
                    {"call_sid": call_sid},
                    {
                        "$set": ch_set,
                        "$setOnInsert": {
                            "created_at": created_at_val,
                        },
                    },
                    upsert=True,
                )
                stats["calls_upserted"] += 1

            lead = await db.leads.find_one(
                {"mobile_digits": mobile_digits},
                {"_id": 0, "id": 1, "assigned_user_id": 1},
            )
            lead_patch = {
                **lead_set,
                "upload_batch_id": upload_batch_id,
                "upload_batch_name": batch_name,
                "updated_at": datetime.utcnow(),
            }
            lead_id: Optional[str] = None

            if lead:
                if dry_run:
                    stats["leads_would_update"] += 1
                else:
                    await db.leads.update_one(
                        {"mobile_digits": mobile_digits},
                        {"$set": lead_patch},
                    )
                    stats["leads_updated"] += 1
                lead_id = lead["id"]
                if _is_unassigned(lead):
                    unassigned_lead_ids.append(lead_id)
                else:
                    stats["assign_skipped_already_assigned"] += 1
            else:
                if dry_run:
                    new_assign_mobiles.add(mobile_digits)
                else:
                    lead_id = str(uuid.uuid4())
                    doc = {
                        "id": lead_id,
                        "full_name": lead_set.get("full_name") or "Unknown",
                        "mobile": lead_set.get("mobile") or "",
                        "mobile_digits": mobile_digits,
                        "status": "Inquiry",
                        "temperature": "Warm",
                        "disposition": lead_set.get("disposition") or "New",
                        "futwork_sync_status": "pending",
                        "created_at": datetime.utcnow(),
                        **lead_patch,
                    }
                    await db.leads.insert_one(doc)
                    stats["leads_created"] += 1
                    new_lead_ids.append(lead_id)

            if not dry_run and lead_id and ch_set.get("lead_id") in ("", None):
                await db.call_history.update_one(
                    {"call_sid": call_sid},
                    {"$set": {"lead_id": lead_id}},
                )

    stats["leads_would_create"] = len(new_assign_mobiles)

    if auto_assign:
        unique_unassigned = list(dict.fromkeys(unassigned_lead_ids))
        stats["assign_candidates"] = len(unique_unassigned) + len(new_assign_mobiles)
        if dry_run:
            stats["would_assign"] = stats["assign_candidates"]
            stats["assigned"] = 0
        else:
            to_assign = list(dict.fromkeys(new_lead_ids + unassigned_lead_ids))
            stats["assign_candidates"] = len(to_assign)
            if to_assign:
                svc = AssignmentService(db)
                for lid in to_assign:
                    rep, _ = await svc.auto_assign_lead(lid)
                    if rep:
                        stats["assigned"] += 1

    if not dry_run:
        await db.lead_upload_history.update_one(
            {"id": upload_batch_id},
            {
                "$set": {
                    "id": upload_batch_id,
                    "batch_name": batch_name,
                    "filename": csv_path.name,
                    "created_at": datetime.utcnow(),
                    "processed": stats["calls_upserted"],
                    "new_leads": stats["leads_created"],
                    "updated_leads": stats["leads_updated"],
                    "unprocessed": stats["failed"],
                    "row_count": stats["rows"],
                    "source": "seed_historical_futwork",
                }
            },
            upsert=True,
        )

    return stats


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed historical Futwork call report CSV")
    parser.add_argument("--csv", type=str, default=str(DEFAULT_CSV))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--assign",
        action="store_true",
        help=(
            "Auto-assign new and existing (unassigned) leads touched by this run; "
            "with --dry-run, reports would_assign without writing assignments"
        ),
    )
    parser.add_argument("--batch-name", type=str, default=BATCH_NAME)
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.is_file():
        print(f"CSV not found: {csv_path}")
        sys.exit(1)

    upload_batch_id = str(uuid.uuid4())
    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "rustomjee_crm")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    print(f"Batch id: {upload_batch_id}")
    print(f"Reading: {csv_path}")
    stats = await seed(
        db,
        csv_path=csv_path,
        upload_batch_id=upload_batch_id,
        batch_name=args.batch_name[:200],
        dry_run=args.dry_run,
        limit=args.limit,
        auto_assign=args.assign,
    )
    print(stats)
    if args.dry_run and args.assign:
        print(f"Would assign {stats.get('would_assign', 0)} leads (no DB writes)")
    if not args.dry_run:
        print(f"Filter leads: /virtual-customer?campaignId={upload_batch_id}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
