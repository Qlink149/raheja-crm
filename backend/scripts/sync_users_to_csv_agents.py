"""
Sync MongoDB users to exactly 1 admin + 36 presales sales accounts from CSV.

Removes placeholder seed users (sales1-5) and any sales login not in the CSV.
Keeps ravinder@rustomjee.com (admin). Re-links lead assignments to CSV agent user ids.

Usage (from backend/):
  python scripts/sync_users_to_csv_agents.py --dry-run
  python scripts/sync_users_to_csv_agents.py
  python scripts/audit_sales_team_counts.py

Also update seed_users.json (admin only) so API restart does not recreate placeholders.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_SCRIPT_DIR, ".."))
sys.path.insert(0, _SCRIPT_DIR)

from app.utils.csv_processor import normalize_agent_name  # noqa: E402
from import_presales_leads_csv import (  # noqa: E402
    ADMIN_EMAIL,
    DEFAULT_CSV,
    _collect_agent_names,
    upsert_agents_from_csv,
)
from seed_users import seed_users  # noqa: E402

load_dotenv()


async def _ensure_admin(db, *, dry_run: bool) -> None:
    if dry_run:
        exists = await db.users.find_one({"email": ADMIN_EMAIL})
        print(f"Admin {ADMIN_EMAIL}: {'exists' if exists else 'would upsert'}")
        return
    await seed_users(db)


async def _delete_non_csv_sales_users(
    db,
    *,
    csv_name_keys: Set[str],
    valid_user_ids: Set[str],
    dry_run: bool,
) -> Dict[str, Any]:
    """Delete role=sales users whose canonical name is not in the CSV agent set."""
    cursor = db.users.find(
        {"role": "sales"},
        {"_id": 0, "id": 1, "email": 1, "full_name": 1, "role": 1},
    )
    to_delete: List[Dict[str, Any]] = []
    async for u in cursor:
        uid = str(u.get("id") or "")
        name_key = normalize_agent_name(u.get("full_name") or "")
        if name_key in csv_name_keys and uid in valid_user_ids:
            continue
        to_delete.append(u)

    deleted_ids = [u["id"] for u in to_delete if u.get("id")]
    lead_refs = 0
    if deleted_ids:
        lead_refs = await db.leads.count_documents({"assigned_user_id": {"$in": deleted_ids}})

    if dry_run:
        return {
            "deleted": 0,
            "would_delete": len(to_delete),
            "deleted_emails": [u.get("email") for u in to_delete],
            "lead_refs_before_remap": lead_refs,
        }

    if to_delete:
        await db.users.delete_many({"id": {"$in": deleted_ids}})
    return {
        "deleted": len(to_delete),
        "would_delete": 0,
        "deleted_emails": [u.get("email") for u in to_delete],
        "lead_refs_before_remap": lead_refs,
    }


async def _relink_lead_assignments(
    db,
    agent_map: Dict[str, str],
    agent_display: Dict[str, str],
    *,
    dry_run: bool,
) -> int:
    """Set assigned_user_id from assigned_to_name / CSV agent keys."""
    updated = 0
    cursor = db.leads.find(
        {},
        {
            "_id": 0,
            "id": 1,
            "assigned_user_id": 1,
            "assigned_to_name": 1,
            "assigned_to": 1,
        },
    )
    async for lead in cursor:
        display = str(
            lead.get("assigned_to_name") or lead.get("assigned_to") or ""
        ).strip()
        if not display:
            continue
        key = normalize_agent_name(display)
        uid = agent_map.get(key)
        if not uid:
            continue
        if lead.get("assigned_user_id") == uid:
            continue
        display_name = agent_display.get(key) or display
        if dry_run:
            updated += 1
            continue
        await db.leads.update_one(
            {"id": lead["id"]},
            {
                "$set": {
                    "assigned_user_id": uid,
                    "assigned_to_name": display_name,
                    "assigned_to": display_name,
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        updated += 1
    return updated


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync users to 1 admin + 36 CSV presales agents"
    )
    parser.add_argument("--csv", type=str, default=str(DEFAULT_CSV))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--default-agent-password",
        type=str,
        default="",
        help="Password for new agents (else SEED_DEFAULT_PASSWORD / rustomjee@123)",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.is_file():
        print(f"CSV not found: {csv_path}")
        sys.exit(1)

    default_pwd = args.default_agent_password or os.getenv(
        "SEED_DEFAULT_PASSWORD", "rustomjee@123"
    )

    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "rustomjee_dash")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    print("=" * 60)
    print("SYNC USERS: 1 admin + 36 CSV sales agents")
    print(f"  dry_run={args.dry_run}")
    print(f"  csv={csv_path.name}")
    print("=" * 60)

    await _ensure_admin(db, dry_run=args.dry_run)

    agent_display = _collect_agent_names(csv_path)
    csv_name_keys = set(agent_display.keys())
    print(f"CSV canonical agents: {len(csv_name_keys)}")

    agent_map, created = await upsert_agents_from_csv(
        db,
        agent_display,
        default_password=default_pwd,
        dry_run=args.dry_run,
    )
    valid_user_ids = set(agent_map.values())
    print(f"Agent map entries: {len(agent_map)} (created/would create: {created})")

    del_stats = await _delete_non_csv_sales_users(
        db,
        csv_name_keys=csv_name_keys,
        valid_user_ids=valid_user_ids,
        dry_run=args.dry_run,
    )
    print(f"Sales users removed: {del_stats}")

    relinked = await _relink_lead_assignments(
        db, agent_map, agent_display, dry_run=args.dry_run
    )
    print(f"Leads assignment relinked: {relinked}")

    if not args.dry_run:
        admin_n = await db.users.count_documents(
            {"email": ADMIN_EMAIL, "role": "admin", "is_active": True}
        )
        sales_n = await db.users.count_documents(
            {"role": "sales", "is_active": True}
        )
        total_n = await db.users.count_documents({"is_active": True})
        print("-" * 60)
        print(f"Admin accounts:  {admin_n}")
        print(f"Sales accounts:  {sales_n}")
        print(f"Total active:    {total_n}")
        print("Expected: admin=1, sales=36, total=37")
        print("-" * 60)
        print("Run: python scripts/audit_sales_team_counts.py")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
