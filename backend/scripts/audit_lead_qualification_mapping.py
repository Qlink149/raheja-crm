"""
Audit lead qualification_category vs match flags and legacy temperature.

Usage (from backend/):
  python scripts/audit_lead_qualification_mapping.py
  python scripts/audit_lead_qualification_mapping.py --output-dir ./audit_out
  python scripts/audit_lead_qualification_mapping.py --phone-suffix 9791 --limit 5000
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import settings  # noqa: E402
from app.utils.lead_qualification_tags import (  # noqa: E402
    expected_qualification_category,
    has_match_flags,
    is_non_contactable_status,
)

load_dotenv()

MISMATCH_TYPES = (
    "qc_stored_ne_expected",
    "warm_with_vip_hot_qualified_qc",
    "legacy_temperature_set",
    "non_contactable_has_tags",
    "has_transcript_no_match_flags",
    "no_qc_no_flags",
)


def _classify_lead(doc: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    status = str(doc.get("status") or "")
    temp = str(doc.get("temperature") or "").strip()
    qc = str(doc.get("qualification_category") or "").strip()

    if is_non_contactable_status(status):
        if temp or qc or doc.get("is_vip"):
            issues.append("non_contactable_has_tags")
        return issues

    exp = expected_qualification_category(doc)
    if exp and qc and qc != exp:
        issues.append("qc_stored_ne_expected")
    if temp == "Warm" and qc in ("VIP Pipeline", "Hot", "Qualified"):
        issues.append("warm_with_vip_hot_qualified_qc")
    if temp in ("Hot", "Warm", "Cold") and qc:
        issues.append("legacy_temperature_set")

    tr = str(doc.get("transcript") or "")
    if len(tr) >= 50 and not has_match_flags(doc):
        issues.append("has_transcript_no_match_flags")
    if not qc and not has_match_flags(doc):
        issues.append("no_qc_no_flags")

    return issues


async def run(
    *,
    output_dir: Path,
    limit: int,
    phone_suffix: str,
    since_days: int,
) -> None:
    if not settings.MONGO_URL:
        print("MONGO_URL is not set.")
        sys.exit(1)

    client = AsyncIOMotorClient(settings.MONGO_URL)
    db = client[settings.DB_NAME]

    query: Dict[str, Any] = {}
    if phone_suffix:
        query["mobile_digits"] = {"$regex": f"{phone_suffix}$"}

    projection = {
        "_id": 0,
        "id": 1,
        "full_name": 1,
        "mobile_digits": 1,
        "status": 1,
        "temperature": 1,
        "qualification_category": 1,
        "budget_match": 1,
        "area_match": 1,
        "timeline_match": 1,
        "budget_category": 1,
        "location_category": 1,
        "source": 1,
        "futwork_sync_status": 1,
        "transcript": 1,
        "is_vip": 1,
    }

    cursor = db.leads.find(query, projection).limit(limit)
    docs = await cursor.to_list(limit)

    issue_counts: Counter = Counter()
    qc_stored: Counter = Counter()
    qc_expected: Counter = Counter()
    by_source: Counter = Counter()
    mismatches: List[Dict[str, Any]] = []

    for doc in docs:
        by_source[str(doc.get("source") or "(none)")] += 1
        qc_stored[str(doc.get("qualification_category") or "(empty)")] += 1
        exp = expected_qualification_category(doc)
        if exp:
            qc_expected[exp] += 1
        for issue in _classify_lead(doc):
            issue_counts[issue] += 1
            mismatches.append(
                {
                    "issue": issue,
                    "id": doc.get("id"),
                    "full_name": doc.get("full_name"),
                    "mobile_digits": doc.get("mobile_digits"),
                    "status": doc.get("status"),
                    "temperature": doc.get("temperature"),
                    "qualification_category": doc.get("qualification_category"),
                    "expected_qc": exp or "",
                    "budget_match": doc.get("budget_match"),
                    "area_match": doc.get("area_match"),
                    "timeline_match": doc.get("timeline_match"),
                    "source": doc.get("source"),
                }
            )

    since = datetime.utcnow() - timedelta(days=since_days)
    ch_query = {
        "created_at": {"$gte": since},
        "transcript": {"$regex": ".{50,}"},
    }
    ch_total = await db.call_history.count_documents(ch_query)
    ch_with_se = await db.call_history.count_documents(
        {**ch_query, "structured_extraction.disposition": {"$exists": True, "$ne": ""}}
    )

    samples = []
    for name in ("Yogansh", "Siddharth", "Mini"):
        row = await db.leads.find_one(
            {"full_name": {"$regex": f"^{name}$", "$options": "i"}},
            {"_id": 0, **projection},
        )
        if row:
            samples.append(
                {
                    "lookup": name,
                    **{k: row.get(k) for k in projection if k != "_id"},
                    "expected_qc": expected_qualification_category(row) or "",
                    "issues": _classify_lead(row),
                }
            )

    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "db_name": settings.DB_NAME,
        "leads_scanned": len(docs),
        "issue_counts": dict(issue_counts),
        "qualification_category_stored": dict(qc_stored),
        "qualification_category_expected_from_flags": dict(qc_expected),
        "by_source": dict(by_source),
        "call_history_last_n_days": since_days,
        "call_history_with_transcript": ch_total,
        "call_history_with_structured_extraction": ch_with_se,
        "samples": samples,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "audit_report.json"
    csv_path = output_dir / "audit_mismatches.csv"

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    if mismatches:
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(mismatches[0].keys()))
            writer.writeheader()
            writer.writerows(mismatches[:50000])

    print(json.dumps(report, indent=2))
    print(f"\nWrote {report_path}")
    if mismatches:
        print(f"Wrote {csv_path} ({len(mismatches)} rows)")
    else:
        print("No mismatches written to CSV.")

    client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit lead QC vs match flags")
    parser.add_argument("--output-dir", type=str, default="audit_out")
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--phone-suffix", type=str, default="")
    parser.add_argument("--since-days", type=int, default=7)
    args = parser.parse_args()
    asyncio.run(
        run(
            output_dir=Path(args.output_dir),
            limit=max(1, args.limit),
            phone_suffix=(args.phone_suffix or "").strip(),
            since_days=max(1, args.since_days),
        )
    )


if __name__ == "__main__":
    main()
