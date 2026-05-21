"""
Re-run OpenAI structured extraction for call_history rows with transcripts.

Usage (from backend/):
  python scripts/reseed_transcript_leads_ai.py --dry-run --limit 10
  python scripts/reseed_transcript_leads_ai.py --limit 100 --since-days 30
  python scripts/reseed_transcript_leads_ai.py --checkpoint reseed_checkpoint.json
  python scripts/reseed_transcript_leads_ai.py --phone-suffix 7338 --limit 10
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Set

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import settings  # noqa: E402
from app.core.time_utils import utc_now  # noqa: E402
from app.services.structured_ai_service import (  # noqa: E402
    StructuredAIService,
    worthy_call_gate,
)
from app.utils.lead_qualification_tags import apply_canonical_tags_to_lead_patch  # noqa: E402
from app.utils.webhook_lead import lead_update_filter, resolve_lead_for_webhook  # noqa: E402

load_dotenv()


def _load_checkpoint(path: Path) -> Set[str]:
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data.get("done_call_ids") or [])
    except Exception:
        return set()


def _save_checkpoint(path: Path, done: Set[str]) -> None:
    path.write_text(
        json.dumps({"done_call_ids": sorted(done)}, indent=2),
        encoding="utf-8",
    )


async def _process_call(
    db,
    svc: StructuredAIService,
    call_doc: Dict[str, Any],
    *,
    dry_run: bool,
) -> str:
    call_id = str(call_doc.get("id") or call_doc.get("call_sid") or "")
    transcript = str(call_doc.get("transcript") or "").strip()
    status_raw = str(call_doc.get("futwork_status") or call_doc.get("status") or "")
    worthy, reasons = worthy_call_gate(status_raw, transcript)
    if not worthy:
        return f"skipped_not_worthy:{','.join(reasons)}"

    if dry_run:
        return "dry_run_would_extract"

    unified = await svc.extract_unified(
        customer_name=str(call_doc.get("customer_name") or "Unknown"),
        phone_number=str(call_doc.get("phone") or call_doc.get("mobile_digits") or ""),
        system_disposition=str(call_doc.get("disposition") or ""),
        recording_url=str(call_doc.get("recording_url") or ""),
        transcript=transcript,
    )
    await db.call_history.update_one(
        {"id": call_id},
        {"$set": svc.to_db_call_history_patch_unified(unified)},
    )

    raw_phone = call_doc.get("phone") or call_doc.get("mobile_digits") or ""
    lead = await resolve_lead_for_webhook(
        db,
        webhook_futwork_id=str(call_doc.get("futwork_lead_id") or ""),
        echo_client_id=str(call_doc.get("client_lead_id") or ""),
        raw_phone=str(raw_phone),
        projection={"_id": 0, "id": 1, "status": 1, "budget_category": 1},
    )
    flt = lead_update_filter(lead)
    if flt:
        lead_patch = apply_canonical_tags_to_lead_patch(
            svc.to_db_lead_patch_unified(unified),
            lead or {},
        )
        lead_patch["updated_at"] = utc_now()
        await db.leads.update_one(
            flt,
            {
                "$set": lead_patch,
                "$unset": {"aiPersonaSummary": "", "strategicNextMove": ""},
            },
        )
    return "ok"


async def run(
    *,
    dry_run: bool,
    limit: int,
    since_days: int,
    checkpoint_path: Path,
    concurrency: int,
    phone_suffix: str = "",
) -> None:
    if not settings.MONGO_URL:
        print("MONGO_URL is not set.")
        sys.exit(1)
    if not dry_run and not settings.OPENAI_API_KEY:
        print("OPENAI_API_KEY is required for reseed.")
        sys.exit(1)

    client = AsyncIOMotorClient(settings.MONGO_URL)
    db = client[settings.DB_NAME]
    svc = StructuredAIService(db)
    done = _load_checkpoint(checkpoint_path)

    since = utc_now() - timedelta(days=since_days)
    query: Dict[str, Any] = {
        "transcript": {"$regex": r".{50,}"},
        "created_at": {"$gte": since},
    }
    if phone_suffix:
        suffix = phone_suffix.strip()
        if suffix:
            query["$or"] = [
                {"phone": {"$regex": f"{suffix}$"}},
                {"mobile_digits": {"$regex": f"{suffix}$"}},
            ]
    cursor = db.call_history.find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
    calls = await cursor.to_list(limit)

    sem = asyncio.Semaphore(max(1, concurrency))
    stats = {"ok": 0, "skip": 0, "err": 0}

    async def one(doc: Dict[str, Any]) -> None:
        cid = str(doc.get("id") or "")
        if cid in done:
            stats["skip"] += 1
            return
        async with sem:
            try:
                result = await _process_call(db, svc, doc, dry_run=dry_run)
                print(f"call={cid} | {result}")
                if result == "ok" or result.startswith("dry_run"):
                    stats["ok"] += 1
                    if not dry_run:
                        done.add(cid)
                        _save_checkpoint(checkpoint_path, done)
                else:
                    stats["skip"] += 1
            except Exception as e:
                stats["err"] += 1
                print(f"call={cid} | ERROR {e}")

    await asyncio.gather(*[one(d) for d in calls])
    print(f"Done. stats={stats} | checkpoint={checkpoint_path}")
    client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Reseed AI extraction from transcripts")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--since-days", type=int, default=90)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--checkpoint", type=str, default="reseed_checkpoint.json")
    parser.add_argument(
        "--phone-suffix",
        type=str,
        default="",
        help="Only calls whose phone/mobile_digits ends with this suffix (e.g. 7338 for Mini)",
    )
    args = parser.parse_args()
    asyncio.run(
        run(
            dry_run=args.dry_run,
            limit=max(1, args.limit),
            since_days=max(1, args.since_days),
            checkpoint_path=Path(args.checkpoint),
            concurrency=max(1, args.concurrency),
            phone_suffix=args.phone_suffix or "",
        )
    )


if __name__ == "__main__":
    main()
