"""One-off diagnose why orphan calls do not link. Run: python scripts/diagnose_orphan_link.py 9791"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.utils.csv_processor import phone_lookup_candidates
from app.utils.webhook_lead import resolve_lead_for_webhook
from motor.motor_asyncio import AsyncIOMotorClient

ORPHAN_QUERY = {
    "$or": [
        {"lead_id": {"$exists": False}},
        {"lead_id": ""},
        {"lead_id": None},
    ],
}


async def main(suffix: str) -> None:
    client = AsyncIOMotorClient(settings.MONGO_URL)
    db = client[settings.DB_NAME]
    query = dict(ORPHAN_QUERY)
    if suffix:
        query["mobile_digits"] = {"$regex": f"{suffix}$"}

    calls = await db.call_history.find(query, {"_id": 0}).sort("created_at", -1).limit(10).to_list(10)
    print(f"Orphan calls: {len(calls)}\n")

    for ch in calls:
        print("---", ch.get("id"))
        print("  phone:", ch.get("phone"), "| mobile_digits:", ch.get("mobile_digits"))
        print("  client_lead_id:", ch.get("client_lead_id"), "| futwork_lead_id:", ch.get("futwork_lead_id"))
        raw = ch.get("phone") or ch.get("to_number") or ch.get("mobile_digits") or ""
        cands = phone_lookup_candidates(raw)
        print("  candidates:", cands)
        for cand in cands:
            n = await db.leads.count_documents({"mobile_digits": cand})
            print(f"    leads with mobile_digits={cand}: {n}")

        md = str(ch.get("mobile_digits") or "")
        if len(md) >= 9:
            suf = md[-9:]
            leads = await db.leads.find(
                {
                    "$or": [
                        {"mobile_digits": {"$regex": f"{suf}$"}},
                        {"mobile": {"$regex": suf}},
                    ]
                },
                {"_id": 0, "id": 1, "mobile": 1, "mobile_digits": 1, "full_name": 1, "client_lead_id": 1},
            ).to_list(10)
            print(f"  suffix leads ({suf}): {len(leads)}")
            for L in leads:
                print("   ", L)

        resolved = await resolve_lead_for_webhook(
            db,
            webhook_futwork_id=str(ch.get("futwork_lead_id") or ""),
            echo_client_id=str(ch.get("client_lead_id") or ""),
            raw_phone=raw,
        )
        print("  resolve_lead_for_webhook:", resolved.get("id") if resolved else None)
        print()

    client.close()


if __name__ == "__main__":
    suf = sys.argv[1] if len(sys.argv) > 1 else "9791"
    asyncio.run(main(suf))
