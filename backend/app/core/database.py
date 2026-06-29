import logging
import uuid
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

from .config import settings

logger = logging.getLogger(__name__)

class Database:
    client: AsyncIOMotorClient = None
    db = None

db_instance = Database()

async def get_db():
    return db_instance.db

async def connect_to_mongo():
    logger.info("Connecting to MongoDB...")
    db_instance.client = AsyncIOMotorClient(settings.MONGO_URL)
    db_instance.db = db_instance.client[settings.DB_NAME]
    logger.info("Connected to MongoDB")

async def close_mongo_connection():
    logger.info("Closing MongoDB connection...")
    db_instance.client.close()
    logger.info("Closed MongoDB connection")

async def _warn_duplicate_mobile_digits(db) -> None:
    """Log if duplicate mobile_digits would block the unique index."""
    try:
        pipeline = [
            {"$match": {"mobile_digits": {"$regex": r"^\d{10}$"}}},
            {"$group": {"_id": "$mobile_digits", "count": {"$sum": 1}}},
            {"$match": {"count": {"$gt": 1}}},
            {"$limit": 5},
        ]
        dups = await db.leads.aggregate(pipeline).to_list(5)
        if dups:
            samples = [d["_id"] for d in dups]
            logger.warning(
                "Duplicate mobile_digits found (%s sample(s): %s). "
                "Dedupe leads before unique mobile_digits index can be enforced.",
                len(dups),
                samples,
            )
    except Exception as e:
        logger.warning("Could not check duplicate mobile_digits: %s", e)


async def initialize_db():
    """Create indexes if they don't exist"""
    db = db_instance.db
    # Lead — identity indexes (mobile_digits is the Raheja business unique key)
    await db.leads.create_index("id", unique=True)
    await db.leads.create_index("mobile")
    await db.leads.create_index("futwork_lead_id")

    # Drop legacy non-unique mobile_digits index before creating unique sparse index
    try:
        idx_info = await db.leads.index_information()
        for idx_name, info in idx_info.items():
            keys = info.get("key", [])
            if not keys or keys[0][0] != "mobile_digits":
                continue
            if not info.get("unique"):
                await db.leads.drop_index(idx_name)
    except Exception:
        pass

    await _warn_duplicate_mobile_digits(db)
    try:
        await db.leads.create_index(
            "mobile_digits",
            unique=True,
            sparse=True,
            name="mobile_digits_unique_sparse",
        )
    except Exception as e:
        logger.warning(
            "Unique mobile_digits index not created (dedupe prod leads if needed): %s",
            e,
        )

    # client_lead_id optional legacy field — non-unique
    try:
        idx_info = await db.leads.index_information()
        for idx_name, info in idx_info.items():
            keys = info.get("key", [])
            if keys and keys[0][0] == "client_lead_id" and info.get("unique"):
                await db.leads.drop_index(idx_name)
                break
    except Exception:
        pass
    await db.leads.create_index("client_lead_id")
    await db.leads.create_index("external_id")
    await db.leads.create_index("campaign_id")
    await db.leads.create_index([("campaign_id", 1), ("futwork_sync_status", 1)])

    # Lead — filter indexes (used by virtual customer page)
    await db.leads.create_index("budget_category")
    await db.leads.create_index("location_category")
    await db.leads.create_index("temperature")
    await db.leads.create_index("qualification_category")
    await db.leads.create_index("intent_category")
    await db.leads.create_index("project")
    await db.leads.create_index([("updated_at", -1)])   # default sort

    # Lead — compound: most common filter combos + sort
    await db.leads.create_index([("budget_category", 1), ("updated_at", -1)])
    await db.leads.create_index([("temperature", 1), ("updated_at", -1)])
    await db.leads.create_index([("location_category", 1), ("updated_at", -1)])
    await db.leads.create_index("assigned_user_id")
    await db.leads.create_index([("assigned_user_id", 1), ("updated_at", -1)])
    await db.leads.create_index("upload_batch_id")
    await db.leads.create_index([("upload_batch_id", 1), ("updated_at", -1)])
    await db.leads.create_index("disposition")
    await db.leads.create_index("sales_qualification")
    await db.leads.create_index([("sales_qualification", 1), ("updated_at", -1)])

    # Lead — full-text search
    try:
        indexes = await db.leads.index_information()
        for idx_name, idx_info in indexes.items():
            if "textIndexVersion" in idx_info:
                if idx_name != "full_name_text_mobile_text_project_text_client_lead_id_text":
                    await db.leads.drop_index(idx_name)
    except Exception:
        pass

    await db.leads.create_index(
        [("full_name", "text"), ("mobile", "text"), ("project", "text"), ("client_lead_id", "text")]
    )

    # Call history indexes
    await db.call_history.create_index("id", unique=True)
    await db.call_history.create_index("mobile_digits")
    await db.call_history.create_index("lead_id")
    await db.call_history.create_index("campaign_id")
    await db.call_history.create_index("campaign")
    await db.call_history.create_index([("created_at", -1)])
    await db.call_history.create_index("upload_batch_id")

    # Upload audit trail (Campaign page)
    await db.lead_upload_history.create_index([("created_at", -1)])
    await db.lead_upload_failures.create_index("upload_id")
    await db.campaigns.create_index("futwork_campaign_id")

    await db.users.create_index("id", unique=True)
    await db.users.create_index("email", unique=True)

    await db.marketing_spends.create_index("id", unique=True)
    await db.marketing_spends.create_index([("project", 1), ("period", 1)])
    await db.marketing_spends.create_index([("channel", 1), ("period", 1)])
    await db.marketing_spends.create_index([("created_at", -1)])

    await db.notifications.create_index("id", unique=True)
    await db.notifications.create_index([("is_read", 1), ("created_at", -1)])
    await db.notifications.create_index(
        [("recipient_user_id", 1), ("is_read", 1), ("created_at", -1)],
        name="notifications_recipient_read_created",
    )
    await db.notifications.create_index("dedupe_key", sparse=True)

    await db.tasks.create_index("id", unique=True)
    await db.tasks.create_index([("status", 1), ("due_date", 1)])
    await db.tasks.create_index("assigned_user_id")

    await db.reminder_rules.create_index("id", unique=True)
    await db.reminders.create_index("dedupe_key", unique=True)
    await db.reminders.create_index([("created_at", -1)])

    await _seed_default_users(db)

    logger.info("Database indexes initialized")


async def _seed_default_users(db):
    """Ensure users from seed_users.json exist (ravinder admin + sales team)."""
    import sys
    from pathlib import Path

    backend_dir = Path(__file__).resolve().parents[2]
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    try:
        from seed_users import seed_users

        n = await seed_users(db)
        if n:
            logger.info("Seeded %s new user(s) from seed_users.json", n)
    except Exception as e:
        logger.warning("User seed skipped: %s", e)
