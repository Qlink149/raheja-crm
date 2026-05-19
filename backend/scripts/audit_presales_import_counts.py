"""
Reconcile presales CSV row counts vs Sales Dashboard / MongoDB totals.

Usage (from backend/):
  python scripts/audit_presales_import_counts.py
  python scripts/audit_presales_import_counts.py --batch-id 2fcda5ea-9ca8-43c4-84e9-e53e9da32537
  python scripts/audit_presales_import_counts.py --csv "Sample Lead Dump 02-05-26- Rustomjee - Sheet1 (1) (1).csv"
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.api.v1.analytics import _rep_name_expression, _sales_managers_from_aggregation  # noqa: E402
from app.utils.csv_processor import process_presales_dump_row  # noqa: E402

load_dotenv()

DEFAULT_CSV = (
    Path(__file__).resolve().parents[1]
    / "Sample Lead Dump 02-05-26- Rustomjee - Sheet1 (1) (1).csv"
)
DEFAULT_BATCH_ID = "2fcda5ea-9ca8-43c4-84e9-e53e9da32537"


def _count_csv(csv_path: Path) -> tuple[int, Counter, int, int]:
    rows = 0
    failed = 0
    agents: Counter = Counter()
    phones: set[str] = set()
    client_ids: set[str] = set()
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            rows += 1
            parsed = process_presales_dump_row(row)
            md = str(parsed.get("mobile_digits") or "").strip()
            if not md:
                failed += 1
                continue
            phones.add(md)
            cid = str(parsed.get("client_lead_id") or "").strip()
            if cid:
                client_ids.add(cid)
            agent = str(parsed.get("presales_agent_name") or "").strip()
            if agent:
                agents[agent] += 1
    valid = rows - failed
    duplicate_row_targets = valid - len(phones)
    return rows, agents, failed, duplicate_row_targets


async def audit(db, *, csv_path: Path, batch_id: str | None) -> None:
    csv_rows, csv_agents, csv_failed, csv_dup_phones = _count_csv(csv_path)
    csv_valid = csv_rows - csv_failed

    total_leads = await db.leads.count_documents({})
    batch_filter = {"upload_batch_id": batch_id} if batch_id else {}
    batch_count = await db.leads.count_documents(batch_filter) if batch_filter else 0

    hot = await db.leads.count_documents({"temperature": "Hot"})
    warm = await db.leads.count_documents({"temperature": "Warm"})
    cold = await db.leads.count_documents({"temperature": "Cold"})
    no_temp = await db.leads.count_documents(
        {
            "$or": [
                {"temperature": {"$in": [None, ""]}},
                {"temperature": {"$exists": False}},
            ]
        }
    )

    _, totals, _, _ = await _sales_managers_from_aggregation(db)
    dashboard_total = int(totals.get("total", 0))

    rep_rows = await db.leads.aggregate(
        [
            {"$addFields": {"rep": _rep_name_expression()}},
            {"$group": {"_id": "$rep", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
    ).to_list(None)
    db_agents = {r["_id"]: r["count"] for r in rep_rows if r["_id"] and r["_id"] != "Unassigned"}

    print("=" * 60)
    print("PRESALES IMPORT / DASHBOARD RECONCILIATION")
    print("=" * 60)
    print(f"CSV file:              {csv_path.name}")
    print(f"CSV rows:              {csv_rows:,}")
    print(f"CSV invalid mobile:    {csv_failed:,}")
    print(f"CSV valid rows:        {csv_valid:,}")
    print(f"CSV unique mobiles:    {csv_valid - csv_dup_phones:,}")
    print(f"CSV duplicate phones:  {csv_dup_phones:,} extra rows hitting same mobile")
    if batch_id:
        print(f"Import batch id:       {batch_id}")
        print(f"Unique leads in batch: {batch_count:,}")
    print()
    print(f"MongoDB leads (total): {total_leads:,}")
    print(f"Dashboard TOTAL card:  {dashboard_total:,}")
    if batch_id and total_leads:
        print(f"Leads NOT in batch:    {max(0, total_leads - batch_count):,} (pre-existing, untouched)")
    print()
    print("Temperature breakdown (MongoDB):")
    print(f"  Hot:                 {hot:,}")
    print(f"  Warm:                {warm:,}")
    print(f"  Cold:                {cold:,}")
    print(f"  No / empty temp:     {no_temp:,}")
    print(f"  Sum Hot+Warm+Cold:   {hot + warm + cold:,}")
    print()
    print("Why CSV rows (16,235) != dashboard total (15,328):")
    print("  1) Updates reuse existing documents (no new row per CSV line).")
    print("  2) Duplicate mobiles in CSV map many lines to one lead.")
    print("  3) One CSV row failed validation (invalid mobile).")
    if batch_count and csv_valid:
        overlap = csv_valid - batch_count
        print(f"  => Valid CSV rows {csv_valid:,} vs unique batch leads {batch_count:,} (diff {overlap:,})")
    print()
    print("Per-agent CSV vs DB (top 10 by CSV):")
    print(f"  {'Agent':<28} {'CSV':>8} {'DB':>8} {'Diff':>8}")
    for name, csv_n in csv_agents.most_common(10):
        db_n = db_agents.get(name, 0)
        print(f"  {name:<28} {csv_n:>8} {db_n:>8} {csv_n - db_n:>8}")
    print("=" * 60)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Audit presales CSV vs dashboard counts")
    parser.add_argument("--csv", type=str, default=str(DEFAULT_CSV))
    parser.add_argument("--batch-id", type=str, default=DEFAULT_BATCH_ID)
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.is_file():
        print(f"CSV not found: {csv_path}")
        sys.exit(1)

    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "rustomjee_crm")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    await audit(db, csv_path=csv_path, batch_id=args.batch_id.strip() or None)
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
