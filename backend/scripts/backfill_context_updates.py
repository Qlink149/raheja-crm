#!/usr/bin/env python3
"""Recompute context_updates for all leads with call_history rows."""

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.context_updates import persist_lead_context_updates  # noqa: E402

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    mongo_url = os.environ.get("MONGO_URL", "")
    db_name = os.environ.get("DB_NAME", "rustomjee_db")
    if not mongo_url:
        print("MONGO_URL is not set.")
        sys.exit(1)

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    try:
        mobile_digits_list = await db.call_history.distinct("mobile_digits")
        lead_ids: set[str] = set()
        for md in mobile_digits_list:
            md = (md or "").strip()
            if not md:
                continue
            async for doc in db.leads.find({"mobile_digits": md}, {"_id": 0, "id": 1}):
                lid = (doc.get("id") or "").strip()
                if lid:
                    lead_ids.add(lid)

        logger.info("Backfilling context_updates for %s leads", len(lead_ids))
        ok = 0
        for lid in sorted(lead_ids):
            try:
                await persist_lead_context_updates(db, lid)
                ok += 1
            except Exception:
                logger.exception("Failed for lead_id=%s", lid)
        logger.info("Done: %s/%s leads updated", ok, len(lead_ids))
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
