"""
Link call_history rows with no lead_id to existing leads (IDs + phone candidates).

When no CRM lead exists for the called number, use --create-missing to insert a stub lead
from call_history + structured_extraction (so Virtual Customer can show budget/disposition).

Run:
  cd backend
  python scripts/link_orphan_call_history.py --dry-run
  python scripts/link_orphan_call_history.py --phone-suffix 9791 --dry-run
  python scripts/link_orphan_call_history.py --phone-suffix 9791 --create-missing
  python scripts/link_orphan_call_history.py --phone-suffix 9791 --create-missing --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any, Dict

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.core.time_utils import utc_now
from app.utils.orphan_call_link import (
    apply_orphan_call_link,
    clear_dry_run_lead_cache,
    resolve_or_link_orphan_call,
)
from motor.motor_asyncio import AsyncIOMotorClient

ORPHAN_QUERY: Dict[str, Any] = {
    "$or": [
        {"lead_id": {"$exists": False}},
        {"lead_id": ""},
        {"lead_id": None},
    ],
}


async def run(
    *,
    dry_run: bool,
    days: int,
    phone_suffix: str,
    limit: int,
    create_missing: bool,
    verbose: bool,
) -> None:
    if not settings.MONGO_URL:
        print("MONGO_URL is not set. Configure backend/.env first.")
        sys.exit(1)

    client = AsyncIOMotorClient(settings.MONGO_URL)
    db = client[settings.DB_NAME]

    query: Dict[str, Any] = dict(ORPHAN_QUERY)
    if days > 0:
        from datetime import timedelta

        since = utc_now() - timedelta(days=days)
        query["created_at"] = {"$gte": since}
    if phone_suffix:
        query["mobile_digits"] = {"$regex": f"{phone_suffix}$"}

    if dry_run:
        clear_dry_run_lead_cache()

    cursor = db.call_history.find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    print(f"Orphan call_history rows to process: {len(docs)}")
    if create_missing:
        print("create-missing: ON (stub leads will be created when no CRM match)")

    linked = 0
    created = 0
    patched = 0
    skipped = 0

    for doc in docs:
        call_id = doc.get("id") or doc.get("call_sid") or ""
        lead, reason = await resolve_or_link_orphan_call(
            db,
            doc,
            create_missing=create_missing,
            dry_run=dry_run,
        )

        if not lead or not lead.get("id"):
            skipped += 1
            if verbose:
                print(f"SKIP call={call_id} | {reason}")
            continue

        has_ai = bool(doc.get("structured_extraction"))
        action = "create" if reason == "created_new" else "link"
        print(
            f"{'[dry-run] ' if dry_run else ''}{action} call={call_id} -> lead={lead['id']} "
            f"({lead.get('client_lead_id', '')})"
            + (f" | AI fields" if has_ai else "")
        )

        ok = await apply_orphan_call_link(db, doc, lead, dry_run=dry_run)
        if not ok:
            skipped += 1
            print(f"  FAILED to apply link for call={call_id}")
            continue

        if reason == "created_new":
            created += 1
        else:
            linked += 1
        if has_ai:
            patched += 1

    print(
        f"Linked existing: {linked} | Created new leads: {created} | "
        f"With AI patch: {patched} | Skipped: {skipped}"
    )
    if skipped and not create_missing:
        print(
            "Tip: If SKIP says 'no_lead_in_db', run again with --create-missing "
            "to add CRM leads from call AI data (budget/disposition)."
        )
    if dry_run:
        print("Dry run — no changes written.")
    client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Link orphan call_history to leads")
    parser.add_argument("--dry-run", action="store_true", help="Print actions only")
    parser.add_argument("--days", type=int, default=30, help="Only calls within last N days")
    parser.add_argument("--phone-suffix", type=str, default="", help="Filter mobile_digits suffix")
    parser.add_argument("--limit", type=int, default=5000, help="Max rows to scan")
    parser.add_argument(
        "--create-missing",
        action="store_true",
        help="Create stub lead in CRM when phone not found (uses structured_extraction)",
    )
    parser.add_argument("--verbose", action="store_true", help="Extra per-row logging")
    args = parser.parse_args()
    asyncio.run(
        run(
            dry_run=args.dry_run,
            days=args.days,
            phone_suffix=(args.phone_suffix or "").strip(),
            limit=max(1, args.limit),
            create_missing=args.create_missing,
            verbose=args.verbose,
        )
    )


if __name__ == "__main__":
    main()
