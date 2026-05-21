"""
One-time import of Rustomjee presales lead dump CSV into MongoDB.

Leads are matched and upserted **only** by `client_lead_id` (CSV Lead Id).
Same mobile with different Lead Ids creates separate lead documents.

Usage (from backend/):
  python scripts/import_presales_leads_csv.py --dry-run
  python scripts/import_presales_leads_csv.py --dry-run --limit 500
  python scripts/import_presales_leads_csv.py --csv "Sample Lead Dump 02-05-26- Rustomjee - Sheet1 (1) (1).csv"

Reseed runbook (after client_lead_id refactor):
  1. Backup MongoDB
  2. python scripts/clear_leads_for_reseed.py --dry-run
  3. python scripts/clear_leads_for_reseed.py
  4. Restart API (recreates indexes; drops unique mobile_digits if present)
  5. python scripts/import_presales_leads_csv.py --csv "Sample Lead Dump ..."
  6. python scripts/audit_presales_import_counts.py --batch-id "<batch-id>"

Expected full seed (~16,235 rows):
  - ~16,234 lead documents (1 row with invalid mobile ".")
  - ~36 presales agents from Presales Agent column
  - ~911 rows share a phone with another row but have different Lead Ids (separate leads)

Enrichment fields (disposition, temperature, VIP, categories) are omitted on insert
and never written on update so existing DB values are preserved.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.security import hash_password  # noqa: E402
from app.utils.csv_processor import (  # noqa: E402
    build_phone_key,
    normalize_agent_name,
    process_presales_dump_row,
    slugify_agent_email,
)
from app.utils.lead_tag_sync import reconcile_temperature_with_status  # noqa: E402

load_dotenv()

DEFAULT_CSV = (
    Path(__file__).resolve().parents[1]
    / "Sample Lead Dump 02-05-26- Rustomjee - Sheet1 (1) (1).csv"
)
BATCH_NAME = "Presales Lead Dump Import"
USER_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
ADMIN_EMAIL = "ravinder@rustomjee.com"
SEED_TEST_EMAILS = [f"sales{i}@rustomjee.com" for i in range(1, 6)]
AGENT_EMAIL_DOMAIN = "rustomjee.com"

LEAD_PROJECTION = {
    "_id": 0,
    "id": 1,
    "client_lead_id": 1,
    "futwork_lead_id": 1,
    "futwork_sync_status": 1,
    "last_call_status": 1,
    "last_call_status_raw": 1,
}


def _user_id_from_email(email: str) -> str:
    return str(uuid.uuid5(USER_NAMESPACE, email.strip().lower()))


def _collect_agent_names(csv_path: Path) -> Dict[str, str]:
    """Return normalized_name -> display name (first seen casing)."""
    agents: Dict[str, str] = {}
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            raw = str(row.get("Presales Agent") or "").strip()
            if not raw or raw == "-":
                continue
            key = normalize_agent_name(raw)
            if key and key not in agents:
                agents[key] = raw
    return agents


def _unique_email(base_email: str, used: Set[str]) -> str:
    email = base_email.lower()
    if email not in used:
        used.add(email)
        return email
    local, _, domain = email.partition("@")
    n = 2
    while True:
        candidate = f"{local}-{n}@{domain}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        n += 1


async def cleanup_test_users(db, *, dry_run: bool) -> Dict[str, int]:
    """Remove seed placeholder sales reps; keep admin. Prefer scripts/sync_users_to_csv_agents.py for full 36+1 sync."""
    filt = {
        "$or": [
            {"email": {"$in": SEED_TEST_EMAILS}},
            {"full_name": {"$regex": r"^Sales Rep \d", "$options": "i"}},
        ],
        "email": {"$ne": ADMIN_EMAIL},
    }
    cursor = db.users.find(filt, {"_id": 0, "id": 1, "email": 1, "full_name": 1})
    to_delete = await cursor.to_list(100)
    lead_refs = 0
    if to_delete:
        ids = [u["id"] for u in to_delete if u.get("id")]
        if ids:
            lead_refs = await db.leads.count_documents({"assigned_user_id": {"$in": ids}})

    if dry_run:
        return {
            "test_users_deleted": 0,
            "test_users_would_delete": len(to_delete),
            "leads_referencing_deleted_users": lead_refs,
        }

    if to_delete:
        await db.users.delete_many(filt)
    return {
        "test_users_deleted": len(to_delete),
        "test_users_would_delete": 0,
        "leads_referencing_deleted_users": lead_refs,
    }


async def upsert_agents_from_csv(
    db,
    agent_names: Dict[str, str],
    *,
    default_password: str,
    dry_run: bool,
) -> Tuple[Dict[str, str], int]:
    """Create/update sales users from CSV agent names. Returns name_key -> user_id."""
    used_emails: Set[str] = set()
    existing_emails = await db.users.distinct("email")
    used_emails.update(e.lower() for e in existing_emails if e)

    name_to_id: Dict[str, str] = {}
    created = 0
    now = datetime.now(timezone.utc).isoformat()
    hashed = hash_password(default_password)

    for key, display_name in sorted(agent_names.items()):
        email = _unique_email(slugify_agent_email(display_name, AGENT_EMAIL_DOMAIN), used_emails)
        uid = _user_id_from_email(email)

        if dry_run:
            existing = await db.users.find_one(
                {"$or": [{"email": email}, {"full_name": display_name}]},
                {"_id": 0, "id": 1},
            )
            if existing:
                name_to_id[key] = existing["id"]
            else:
                name_to_id[key] = uid
                created += 1
            continue

        existing = await db.users.find_one(
            {"full_name": display_name},
            {"_id": 0, "id": 1, "email": 1},
        )
        if existing:
            name_to_id[key] = existing["id"]
            await db.users.update_one(
                {"id": existing["id"]},
                {
                    "$set": {
                        "full_name": display_name,
                        "role": "sales",
                        "is_active": True,
                        "updated_at": now,
                    }
                },
            )
            continue

        doc = {
            "id": uid,
            "email": email,
            "full_name": display_name,
            "role": "sales",
            "hashed_password": hashed,
            "is_active": True,
            "current_session_id": None,
            "created_at": now,
            "updated_at": now,
        }
        await db.users.update_one({"email": email}, {"$set": doc}, upsert=True)
        name_to_id[key] = uid
        created += 1

    return name_to_id, created


async def _load_lead_maps(db) -> Tuple[Dict[str, Dict], int]:
    by_client: Dict[str, Dict] = {}
    conflicts = 0

    cursor = db.leads.find({}, LEAD_PROJECTION)
    async for doc in cursor:
        lid = doc.get("id")
        if not lid:
            continue

        cid = str(doc.get("client_lead_id") or "").strip()
        if cid:
            if cid in by_client and by_client[cid]["id"] != lid:
                conflicts += 1
            else:
                by_client[cid] = doc

    return by_client, conflicts


def _find_existing(
    parsed: Dict[str, Any],
    by_client: Dict[str, Dict],
) -> Optional[Dict[str, Any]]:
    """Match lead by client_lead_id only."""
    cid = str(parsed.get("client_lead_id") or "").strip()
    if not cid:
        return None
    return by_client.get(cid)


def _build_lead_patch(
    parsed: Dict[str, Any],
    *,
    existing: Optional[Dict[str, Any]],
    agent_map: Dict[str, str],
    upload_batch_id: str,
    batch_name: str,
    is_insert: bool,
) -> Dict[str, Any]:
    """
    CSV-owned fields only. On update: client_lead_id + agent assignment only
    (plus upload metadata). Status, enrichment, project, phone, name stay as in DB.
    On insert: full CSV contact/project/status; enrichment omitted (empty).
    """
    presales_status = str(parsed.get("presales_status") or "").strip()
    agent_display = str(parsed.get("presales_agent_name") or "").strip()
    agent_key = normalize_agent_name(agent_display)

    patch: Dict[str, Any] = {
        "client_lead_id": parsed.get("client_lead_id") or "",
        "upload_batch_id": upload_batch_id,
        "upload_batch_name": batch_name,
        "updated_at": datetime.utcnow(),
    }

    if is_insert:
        patch.update(
            {
                "country": parsed.get("country") or "",
                "country_code": parsed.get("country_code") or "",
                "mobile": parsed.get("mobile") or "",
                "mobile_digits": parsed.get("mobile_digits") or "",
                "phone_key": parsed.get("phone_key") or "",
                "project": parsed.get("project") or "",
            }
        )
    last_name = str(parsed.get("last_name") or "").strip()
    if last_name and is_insert:
        patch["full_name"] = last_name
        patch["last_name"] = last_name

    if presales_status and is_insert:
        patch["status"] = presales_status

    if agent_key and agent_key in agent_map:
        uid = agent_map[agent_key]
        patch["assigned_user_id"] = uid
        patch["assigned_to"] = agent_display
        patch["assigned_to_name"] = agent_display
        patch["assigned_at"] = datetime.utcnow()

    if is_insert:
        patch["futwork_sync_status"] = "pending"

    return reconcile_temperature_with_status(patch)


def _register_lead_in_maps(doc: Dict[str, Any], by_client: Dict[str, Dict]) -> None:
    lid = doc.get("id")
    if not lid:
        return
    slim = {k: doc.get(k) for k in LEAD_PROJECTION if k != "_id"}
    slim["id"] = lid

    cid = str(slim.get("client_lead_id") or "").strip()
    if cid:
        by_client[cid] = slim


async def import_presales_csv(
    db,
    *,
    csv_path: Path,
    upload_batch_id: str,
    batch_name: str,
    agent_map: Dict[str, str],
    dry_run: bool = False,
    limit: Optional[int] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    stats: Dict[str, Any] = {
        "rows": 0,
        "leads_created": 0,
        "leads_updated": 0,
        "failed": 0,
        "conflicts": 0,
        "bulk_batches": 0,
        "preload_map_conflicts": 0,
    }
    failures: List[Dict[str, Any]] = []

    by_client, preload_conflicts = await _load_lead_maps(db)
    stats["preload_map_conflicts"] = preload_conflicts

    ops: List[UpdateOne] = []

    async def flush_ops() -> None:
        nonlocal ops
        if not ops:
            return
        if not dry_run:
            await db.leads.bulk_write(ops, ordered=False)
        stats["bulk_batches"] += 1
        ops = []

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            if limit is not None and idx >= limit:
                break
            stats["rows"] += 1
            try:
                parsed = process_presales_dump_row(row)
            except Exception as exc:
                stats["failed"] += 1
                failures.append({"row_index": idx, "reason": str(exc)})
                continue

            client_lead_id = str(parsed.get("client_lead_id") or "").strip()
            if not client_lead_id:
                stats["failed"] += 1
                failures.append({"row_index": idx, "reason": "missing client_lead_id"})
                continue

            mobile_digits = str(parsed.get("mobile_digits") or "").strip()
            if not mobile_digits:
                stats["failed"] += 1
                failures.append({"row_index": idx, "reason": "missing mobile"})
                continue

            existing = _find_existing(parsed, by_client)

            is_insert = existing is None
            patch = _build_lead_patch(
                parsed,
                existing=existing,
                agent_map=agent_map,
                upload_batch_id=upload_batch_id,
                batch_name=batch_name,
                is_insert=is_insert,
            )

            if is_insert:
                lead_id = str(uuid.uuid4())
                patch["id"] = lead_id
                patch["created_at"] = datetime.utcnow()
                filt: Dict[str, Any] = {"id": lead_id}
                update_doc: Dict[str, Any] = {"$set": patch}
                stats["leads_created"] += 1
                if not dry_run:
                    ops.append(UpdateOne(filt, update_doc, upsert=True))
                _register_lead_in_maps(patch, by_client)
            else:
                lead_id = existing["id"]
                filt = {"id": lead_id}
                if str(existing.get("futwork_lead_id") or "").strip():
                    patch.pop("futwork_lead_id", None)
                stats["leads_updated"] += 1
                if not dry_run:
                    ops.append(UpdateOne(filt, {"$set": patch}))
                merged = {**existing, **patch, "id": lead_id}
                _register_lead_in_maps(merged, by_client)

            if len(ops) >= batch_size:
                await flush_ops()

    await flush_ops()

    if failures and not dry_run:
        await db.lead_upload_failures.insert_one(
            {
                "upload_id": upload_batch_id,
                "created_at": datetime.utcnow(),
                "failures": failures[:500],
                "total_failures": len(failures),
            }
        )

    if not dry_run:
        await db.lead_upload_history.update_one(
            {"id": upload_batch_id},
            {
                "$set": {
                    "id": upload_batch_id,
                    "batch_name": batch_name,
                    "filename": csv_path.name,
                    "created_at": datetime.utcnow(),
                    "processed": stats["rows"] - stats["failed"],
                    "new_leads": stats["leads_created"],
                    "updated_leads": stats["leads_updated"],
                    "unprocessed": stats["failed"],
                    "row_count": stats["rows"],
                    "conflicts": stats["conflicts"],
                    "source": "import_presales_leads_csv",
                }
            },
            upsert=True,
        )

    stats["failure_samples"] = len(failures)
    return stats


async def main() -> None:
    parser = argparse.ArgumentParser(description="Import presales lead dump CSV")
    parser.add_argument("--csv", type=str, default=str(DEFAULT_CSV))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--skip-user-cleanup", action="store_true")
    parser.add_argument("--batch-name", type=str, default=BATCH_NAME)
    parser.add_argument(
        "--default-agent-password",
        type=str,
        default="",
        help="Default password for newly created agent users (else SEED_DEFAULT_PASSWORD / rustomjee@123)",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.is_file():
        print(f"CSV not found: {csv_path}")
        sys.exit(1)

    default_pwd = (
        args.default_agent_password
        or os.getenv("SEED_DEFAULT_PASSWORD", "rustomjee@123")
    )
    upload_batch_id = str(uuid.uuid4())
    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "rustomjee_crm")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    print(f"Batch id: {upload_batch_id}")
    print(f"Reading: {csv_path}")
    print(f"Dry run: {args.dry_run}")

    agent_names = _collect_agent_names(csv_path)
    print(f"Unique presales agents in CSV: {len(agent_names)}")

    if not args.skip_user_cleanup:
        user_stats = await cleanup_test_users(db, dry_run=args.dry_run)
        print(f"Test user cleanup: {user_stats}")

    agent_map, agents_created = await upsert_agents_from_csv(
        db,
        agent_names,
        default_password=default_pwd,
        dry_run=args.dry_run,
    )
    print(f"Agent users created: {agents_created}")

    stats = await import_presales_csv(
        db,
        csv_path=csv_path,
        upload_batch_id=upload_batch_id,
        batch_name=args.batch_name[:200],
        agent_map=agent_map,
        dry_run=args.dry_run,
        limit=args.limit,
        batch_size=args.batch_size,
    )
    print(stats)
    if not args.dry_run:
        print(f"Filter leads: upload_batch_id={upload_batch_id}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
