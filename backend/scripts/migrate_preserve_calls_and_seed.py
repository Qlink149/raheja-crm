"""
Migrate to client_lead_id identity WITHOUT wiping call_history or AI enrichment.

What this does:
  1. Drops unique index on mobile_digits (phone is no longer unique).
  2. Parses the presales CSV (~16,235 rows) and upserts every row by client_lead_id.
  3. Before import, snapshots existing leads that have calls / Futwork / AI fields.
  4. Maps each enriched legacy lead -> target client_lead_id (phone may map to multiple CSV ids).
  5. Preserves internal UUID (frontend /customer/:id) and enrichment on the matching CSV row.
  6. Deletes orphan leads (old phone-collapsed docs not in CSV) — call_history is NOT deleted.

What is preserved:
  - call_history collection (all transcripts, structured_extraction on calls, recordings).
  - users, campaigns, marketing, notifications.

Usage (from backend/):
  python scripts/migrate_preserve_calls_and_seed.py --dry-run
  python scripts/migrate_preserve_calls_and_seed.py
  python scripts/migrate_preserve_calls_and_seed.py --csv "Sample Lead Dump 02-05-26- Rustomjee - Sheet1 (1) (1).csv"

Recommended: mongodump backup first.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_SCRIPT_DIR, ".."))
sys.path.insert(0, _SCRIPT_DIR)

from app.utils.csv_processor import process_presales_dump_row  # noqa: E402

from import_presales_leads_csv import (  # noqa: E402
    DEFAULT_CSV,
    _build_lead_patch,
    _collect_agent_names,
    cleanup_test_users,
    upsert_agents_from_csv,
)

load_dotenv()

BATCH_NAME = "Client Lead ID migration (preserve calls)"

# Fields copied from legacy leads onto the CSV row (never cleared by CSV update).
ENRICHMENT_FIELDS = (
    "temperature",
    "disposition",
    "transcript",
    "last_call_date",
    "last_call_status",
    "last_call_status_raw",
    "last_call_duration",
    "last_recording_url",
    "last_structured_call_sid",
    "futwork_lead_id",
    "futwork_sync_status",
    "structured_extraction",
    "ai_disposition",
    "ai_worthy",
    "aiPersonaSummary",
    "strategicNextMove",
    "lastCallSummary",
    "qualification_category",
    "budget_category",
    "location_category",
    "intent_category",
    "is_vip",
    "is_hni",
    "vip_category",
    "budget_match",
    "area_match",
    "timeline_match",
    "configuration",
    "current_residence_type",
    "current_residence_location",
    "current_residential_location",
    "possession_requirement",
    "reason_for_purchase",
    "presales_description",
    "context_summary",
    "suggested_next_project",
    "next_action_date",
    "sales_qualification",
    "sales_qualified_at",
    "sales_qualified_by",
    "campaign_id",
    "email",
    "intent",
    "location",
    "source",
    "budget",
    "designation",
    "ethnicity",
    "carpet_area",
    "bhk",
    "first_name",
    "call_status",
    "status",
)

FUTWORK_RANK = {"pushed": 3, "failed": 2, "pending": 1}


def _has_value(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return True


def _futwork_rank(status: Any) -> int:
    return FUTWORK_RANK.get(str(status or "").lower(), 0)


def _merge_enrichment(dst: Dict[str, Any], src: Dict[str, Any]) -> None:
    """Merge src into dst; prefer stronger Futwork / non-empty values."""
    for key in ENRICHMENT_FIELDS:
        new_v = src.get(key)
        if not _has_value(new_v):
            continue
        old_v = dst.get(key)
        if key == "futwork_sync_status":
            if _futwork_rank(new_v) >= _futwork_rank(old_v):
                dst[key] = new_v
            continue
        if not _has_value(old_v):
            dst[key] = new_v
        elif key in ("transcript", "structured_extraction") and len(str(new_v)) > len(str(old_v)):
            dst[key] = new_v


def _lead_is_enriched(
    lead: Dict[str, Any],
    phones_with_calls: Set[str],
    futwork_ids_with_calls: Set[str],
) -> bool:
    md = str(lead.get("mobile_digits") or "").strip()
    fw = str(lead.get("futwork_lead_id") or "").strip()
    if md and md in phones_with_calls:
        return True
    if fw and fw in futwork_ids_with_calls:
        return True
    if str(lead.get("futwork_sync_status") or "").lower() in ("pushed", "failed"):
        return True
    if _has_value(lead.get("last_call_date")) or _has_value(lead.get("last_call_status")):
        return True
    if _has_value(lead.get("transcript")):
        return True
    if _has_value(lead.get("structured_extraction")):
        return True
    if _has_value(lead.get("aiPersonaSummary")) or _has_value(lead.get("lastCallSummary")):
        return True
    temp = str(lead.get("temperature") or "").strip()
    if temp and temp.lower() not in ("warm", ""):
        return True
    if lead.get("is_vip") or lead.get("is_hni"):
        return True
    qual = str(lead.get("qualification_category") or "").strip()
    if qual and qual != "Other":
        return True
    return False


def _build_csv_index(csv_path: Path) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, List[str]], Set[str]]:
    """parsed_by_cid, phone_to_cids (sorted), valid_cids."""
    parsed_by_cid: Dict[str, Dict[str, Any]] = {}
    phone_to_cids: Dict[str, List[str]] = defaultdict(list)

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                parsed = process_presales_dump_row(row)
            except Exception:
                continue
            cid = str(parsed.get("client_lead_id") or "").strip()
            if not cid:
                continue
            md = str(parsed.get("mobile_digits") or "").strip()
            if not md:
                continue
            parsed_by_cid[cid] = parsed
            if cid not in phone_to_cids[md]:
                phone_to_cids[md].append(cid)

    for md in phone_to_cids:
        phone_to_cids[md] = sorted(phone_to_cids[md])

    return parsed_by_cid, dict(phone_to_cids), set(parsed_by_cid.keys())


def resolve_target_client_lead_id(
    old: Dict[str, Any],
    *,
    valid_cids: Set[str],
    phone_to_cids: Dict[str, List[str]],
) -> Optional[str]:
    cid = str(old.get("client_lead_id") or old.get("external_id") or "").strip()
    if cid and cid in valid_cids:
        return cid

    md = str(old.get("mobile_digits") or "").strip()
    if not md:
        return None

    cids = phone_to_cids.get(md) or []
    if not cids:
        return None
    if len(cids) == 1:
        return cids[0]

    if cid and cid in cids:
        return cid
    ext = str(old.get("external_id") or "").strip()
    if ext and ext in cids:
        return ext

    # Multiple CSV leads share this phone — attach enrichment to stable first id; log count later.
    return cids[0]


async def _load_call_phone_sets(db) -> Tuple[Set[str], Set[str]]:
    phones = set(
        await db.call_history.distinct(
            "mobile_digits",
            {"mobile_digits": {"$nin": [None, ""]}},
        )
    )
    futwork_ids = set(
        await db.call_history.distinct(
            "lead_id",
            {"lead_id": {"$nin": [None, ""]}},
        )
    )
    return phones, futwork_ids


async def _snapshot_legacy_maps(
    db,
    *,
    valid_cids: Set[str],
    phone_to_cids: Dict[str, List[str]],
    phones_with_calls: Set[str],
    futwork_ids_with_calls: Set[str],
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str], Dict[str, int]]:
    """
    enrichment_by_cid, uuid_by_cid (preserve /customer/:id), ambiguous_phone_attachments.
    """
    enrichment_by_cid: Dict[str, Dict[str, Any]] = {}
    uuid_by_cid: Dict[str, str] = {}
    ambiguous: Dict[str, int] = defaultdict(int)

    cursor = db.leads.find({})
    async for old in cursor:
        old = dict(old)
        if old.get("_id") is not None:
            old.pop("_id", None)

        target = resolve_target_client_lead_id(
            old, valid_cids=valid_cids, phone_to_cids=phone_to_cids
        )
        if not target:
            continue

        md = str(old.get("mobile_digits") or "").strip()
        cids_for_phone = phone_to_cids.get(md) or []
        if len(cids_for_phone) > 1 and target == cids_for_phone[0]:
            ambiguous[md] += 1

        if not _lead_is_enriched(old, phones_with_calls, futwork_ids_with_calls):
            # Still reserve UUID if this was the only DB row for that client_lead_id.
            if str(old.get("client_lead_id") or "").strip() == target and old.get("id"):
                uuid_by_cid.setdefault(target, old["id"])
            continue

        bucket = enrichment_by_cid.setdefault(target, {})
        _merge_enrichment(bucket, old)

        lid = str(old.get("id") or "").strip()
        if lid:
            prev = uuid_by_cid.get(target)
            if not prev:
                uuid_by_cid[target] = lid
            elif _futwork_rank(old.get("futwork_sync_status")) > _futwork_rank(
                enrichment_by_cid.get(target, {}).get("futwork_sync_status")
            ):
                uuid_by_cid[target] = lid

    return enrichment_by_cid, uuid_by_cid, dict(ambiguous)


async def drop_mobile_unique_index(db, *, dry_run: bool) -> None:
    indexes = await db.leads.index_information()
    for name, info in indexes.items():
        keys = info.get("key", [])
        is_mobile = keys == [("mobile_digits", 1)] or (
            len(keys) == 1 and keys[0][0] == "mobile_digits"
        )
        if is_mobile and info.get("unique"):
            print(f"  drop unique index: {name}")
            if not dry_run:
                await db.leads.drop_index(name)


async def ensure_post_migration_indexes(db, *, dry_run: bool) -> None:
    if dry_run:
        print("  would ensure: client_lead_id unique (non-sparse), mobile_digits non-unique")
        return

    indexes = await db.leads.index_information()
    for name, info in indexes.items():
        keys = info.get("key", [])
        is_cid = keys == [("client_lead_id", 1)] or (
            len(keys) == 1 and keys[0][0] == "client_lead_id"
        )
        if is_cid and (info.get("sparse") or not info.get("unique")):
            print(f"  drop client_lead_id index (sparse/non-unique): {name}")
            await db.leads.drop_index(name)

    await db.leads.create_index("mobile_digits")
    await db.leads.create_index("client_lead_id", unique=True)
    print("  created client_lead_id unique index (non-sparse)")


async def run_migration(
    db,
    *,
    csv_path: Path,
    upload_batch_id: str,
    batch_name: str,
    agent_map: Dict[str, str],
    dry_run: bool,
    batch_size: int,
    limit: Optional[int],
) -> Dict[str, Any]:
    stats: Dict[str, Any] = {
        "csv_rows": 0,
        "csv_valid": 0,
        "leads_upserted": 0,
        "enriched_cids": 0,
        "uuids_preserved": 0,
        "orphans_deleted": 0,
        "ambiguous_phone_enrichments": 0,
        "call_history_kept": 0,
    }

    parsed_by_cid, phone_to_cids, valid_cids = _build_csv_index(csv_path)
    stats["csv_valid"] = len(valid_cids)

    phones_with_calls, futwork_ids_with_calls = await _load_call_phone_sets(db)
    stats["call_history_kept"] = await db.call_history.count_documents({})

    enrichment_by_cid, uuid_by_cid, ambiguous = await _snapshot_legacy_maps(
        db,
        valid_cids=valid_cids,
        phone_to_cids=phone_to_cids,
        phones_with_calls=phones_with_calls,
        futwork_ids_with_calls=futwork_ids_with_calls,
    )
    stats["enriched_cids"] = len(enrichment_by_cid)
    stats["uuids_preserved"] = len(uuid_by_cid)
    stats["ambiguous_phone_enrichments"] = sum(ambiguous.values())

    by_client: Dict[str, Dict] = {}
    cursor = db.leads.find({"client_lead_id": {"$in": list(valid_cids)}}, {"_id": 0, "id": 1, "client_lead_id": 1})
    async for doc in cursor:
        cid = str(doc.get("client_lead_id") or "").strip()
        if cid:
            by_client[cid] = doc

    ops: List[UpdateOne] = []
    row_i = 0

    async def flush() -> None:
        nonlocal ops
        if not ops or dry_run:
            ops = []
            return
        await db.leads.bulk_write(ops, ordered=False)
        stats["leads_upserted"] += len(ops)
        ops = []

    for cid, parsed in parsed_by_cid.items():
        if limit is not None and row_i >= limit:
            break
        row_i += 1
        stats["csv_rows"] += 1

        existing = by_client.get(cid)
        is_insert = existing is None
        patch = _build_lead_patch(
            parsed,
            existing=existing,
            agent_map=agent_map,
            upload_batch_id=upload_batch_id,
            batch_name=batch_name,
            is_insert=is_insert,
        )
        patch["client_lead_id"] = cid
        patch["external_id"] = cid

        enrich = enrichment_by_cid.get(cid)
        if enrich:
            for k, v in enrich.items():
                if _has_value(v):
                    patch[k] = v

        lead_uuid = uuid_by_cid.get(cid) or (existing or {}).get("id") or str(uuid.uuid4())

        if is_insert:
            patch["id"] = lead_uuid
            patch["created_at"] = datetime.now(timezone.utc)
            filt = {"client_lead_id": cid}
            update_doc: Dict[str, Any] = {"$set": patch}
            if not dry_run:
                ops.append(UpdateOne(filt, update_doc, upsert=True))
            by_client[cid] = {"id": lead_uuid, "client_lead_id": cid}
        else:
            filt = {"client_lead_id": cid}
            if not dry_run:
                ops.append(UpdateOne(filt, {"$set": patch}))
            by_client[cid] = {**(existing or {}), **patch, "id": existing["id"]}

        if len(ops) >= batch_size:
            await flush()

    await flush()

    if not dry_run:
        orphan_filter = {
            "$or": [
                {"client_lead_id": {"$exists": False}},
                {"client_lead_id": {"$in": [None, ""]}},
                {"client_lead_id": {"$nin": list(valid_cids)}},
            ]
        }
        res = await db.leads.delete_many(orphan_filter)
        stats["orphans_deleted"] = res.deleted_count

        await ensure_post_migration_indexes(db, dry_run=False)

        await db.lead_upload_history.update_one(
            {"id": upload_batch_id},
            {
                "$set": {
                    "id": upload_batch_id,
                    "batch_name": batch_name,
                    "filename": csv_path.name,
                    "created_at": datetime.now(timezone.utc),
                    "processed": stats["csv_rows"],
                    "new_leads": stats["csv_valid"],
                    "source": "migrate_preserve_calls_and_seed",
                }
            },
            upsert=True,
        )
    else:
        orphan_count = await db.leads.count_documents(
            {
                "$or": [
                    {"client_lead_id": {"$exists": False}},
                    {"client_lead_id": {"$in": [None, ""]}},
                    {"client_lead_id": {"$nin": list(valid_cids)}},
                ]
            }
        )
        stats["orphans_would_delete"] = orphan_count
        await ensure_post_migration_indexes(db, dry_run=True)

    stats["final_lead_count"] = await db.leads.count_documents({}) if not dry_run else None
    stats["expected_leads"] = len(valid_cids)
    return stats


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate to client_lead_id, seed full CSV, preserve calls/AI enrichment"
    )
    parser.add_argument("--csv", type=str, default=str(DEFAULT_CSV))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--skip-user-cleanup", action="store_true")
    parser.add_argument("--skip-agents", action="store_true")
    parser.add_argument("--batch-name", type=str, default=BATCH_NAME)
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.is_file():
        print(f"CSV not found: {csv_path}")
        sys.exit(1)

    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "rustomjee_dash")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    upload_batch_id = str(uuid.uuid4())
    default_pwd = os.getenv("SEED_DEFAULT_PASSWORD", "rustomjee@123")

    print("=" * 60)
    print("Migrate: client_lead_id + full CSV seed + preserve calls")
    print(f"  dry_run={args.dry_run}")
    print(f"  csv={csv_path.name}")
    print(f"  batch_id={upload_batch_id}")
    print("=" * 60)

    if not args.dry_run:
        print("\nWARNING: This modifies leads and deletes orphan lead docs.")
        print("call_history is NOT deleted. Take a mongodump backup first.\n")

    if not args.skip_agents:
        agent_names = _collect_agent_names(csv_path)
        if not args.skip_user_cleanup:
            print("Test user cleanup:", await cleanup_test_users(db, dry_run=args.dry_run))
        agent_map, created = await upsert_agents_from_csv(
            db, agent_names, default_password=default_pwd, dry_run=args.dry_run
        )
        print(f"Agents created: {created}")
    else:
        agent_map = {}

    await drop_mobile_unique_index(db, dry_run=args.dry_run)

    stats = await run_migration(
        db,
        csv_path=csv_path,
        upload_batch_id=upload_batch_id,
        batch_name=args.batch_name[:200],
        agent_map=agent_map,
        dry_run=args.dry_run,
        batch_size=args.batch_size,
        limit=args.limit,
    )

    print("\n--- Results ---")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")

    if stats.get("ambiguous_phone_enrichments"):
        print(
            "\nNote: Some phones map to multiple CSV Lead Ids; call/AI enrichment was "
            "attached to the first Lead Id for that phone. call_history rows are unchanged."
        )

    if not args.dry_run:
        print(f"\nAudit: python scripts/audit_presales_import_counts.py --batch-id {upload_batch_id}")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
