"""
Reconcile presales agent counts: CSV vs users collection vs leads assignment.

Usage (from backend/):
  python scripts/audit_sales_team_counts.py
  python scripts/audit_sales_team_counts.py --csv "Sample Lead Dump 02-05-26- Rustomjee - Sheet1 (1) (1).csv"
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.api.v1.analytics import _rep_name_expression, _is_invalid_rep_name  # noqa: E402
from app.utils.csv_processor import normalize_agent_name  # noqa: E402

load_dotenv()

DEFAULT_CSV = (
    Path(__file__).resolve().parents[1]
    / "Sample Lead Dump 02-05-26- Rustomjee - Sheet1 (1) (1).csv"
)


def _csv_agents(csv_path: Path) -> dict[str, str]:
    """canonical key -> display name (first seen)."""
    agents: dict[str, str] = {}
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            raw = str(row.get("Presales Agent") or "").strip()
            if not raw or raw == "-":
                continue
            key = normalize_agent_name(raw)
            if key and key not in agents:
                agents[key] = raw
    return agents


async def _lead_rep_names(db) -> dict[str, list[str]]:
    """canonical key -> list of display names on leads."""
    by_key: dict[str, list[str]] = defaultdict(list)
    rows = await db.leads.aggregate(
        [
            {"$addFields": {"rep": _rep_name_expression()}},
            {"$group": {"_id": "$rep", "count": {"$sum": 1}}},
        ]
    ).to_list(None)
    for r in rows:
        name = str(r.get("_id") or "").strip()
        if not name or name == "Unassigned" or _is_invalid_rep_name(name):
            continue
        key = normalize_agent_name(name)
        if name not in by_key[key]:
            by_key[key].append(name)
    return dict(by_key)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Audit sales team counts")
    parser.add_argument("--csv", type=str, default=str(DEFAULT_CSV))
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.is_file():
        print(f"CSV not found: {csv_path}")
        sys.exit(1)

    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "rustomjee_dash")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    csv_agents = _csv_agents(csv_path)
    lead_agents = await _lead_rep_names(db)

    users = await db.users.find(
        {"role": "sales", "is_active": True},
        {"_id": 0, "email": 1, "full_name": 1},
    ).to_list(500)

    raw_lead_names = sum(len(v) for v in lead_agents.values())
    canonical_leads = len(lead_agents)

    print("=" * 60)
    print("SALES TEAM COUNT AUDIT")
    print("=" * 60)
    print(f"CSV unique agents (canonical):     {len(csv_agents):>5}")
    print(f"Leads distinct display names:    {raw_lead_names:>5}")
    print(f"Leads canonical agents:          {canonical_leads:>5}")
    print(f"users (role=sales, active):      {len(users):>5}")
    admin_n = await db.users.count_documents(
        {"role": "admin", "is_active": True, "email": "ravinder@rustomjee.com"}
    )
    total_logins = len(users) + admin_n
    print(f"users (admin ravinder, active):  {admin_n:>5}")
    print(f"Total login accounts:          {total_logins:>5}  (target: 37)")
    print()

    only_csv = set(csv_agents) - set(lead_agents)
    only_leads = set(lead_agents) - set(csv_agents)
    collisions = {k: v for k, v in lead_agents.items() if len(v) > 1}

    if only_csv:
        print(f"In CSV but not on leads ({len(only_csv)}):")
        for k in sorted(only_csv)[:15]:
            print(f"  - {csv_agents[k]}")
    if only_leads:
        print(f"On leads but not in CSV ({len(only_leads)}):")
        for k in sorted(only_leads)[:15]:
            print(f"  - {lead_agents[k][0]}")
    if collisions:
        print(f"\nName variants on leads ({len(collisions)} agents):")
        for k, variants in sorted(collisions.items(), key=lambda x: -len(x[1]))[:10]:
            print(f"  {variants[0]!r} <- {variants}")

    extra_users = [
        u
        for u in users
        if normalize_agent_name(u.get("full_name") or "")
        not in csv_agents
        and normalize_agent_name(u.get("full_name") or "") not in lead_agents
    ]
    if extra_users:
        print(f"\nExtra user accounts not in CSV/leads ({len(extra_users)}):")
        for u in extra_users[:10]:
            print(f"  - {u.get('full_name')} <{u.get('email')}>")

    print("=" * 60)
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
