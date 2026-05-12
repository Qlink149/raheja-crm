import logging
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

async def initialize_db():
    """Create indexes if they don't exist"""
    db = db_instance.db
    # Lead — identity indexes
    await db.leads.create_index("id", unique=True)
    try:
        await db.leads.create_index("mobile_digits", unique=True)
    except Exception as e:
        logger.warning(
            "Could not ensure unique index on leads.mobile_digits (duplicate phones may exist; "
            "run backend/scripts/dedupe_leads_by_mobile.py --execute): %s",
            e,
        )
        await db.leads.create_index("mobile_digits")
    await db.leads.create_index("mobile")
    await db.leads.create_index("_seed_key")
    # Covers the OR-arm in the Futwork webhook lead lookup (futwork_lead_id).
    await db.leads.create_index("futwork_lead_id")
    await db.leads.create_index("campaign_id")
    await db.leads.create_index([("campaign_id", 1), ("futwork_sync_status", 1)])

    # Lead — filter indexes (used by virtual customer page)
    await db.leads.create_index("budget_category")
    await db.leads.create_index("location_category")
    await db.leads.create_index("temperature")
    await db.leads.create_index("qualification_category")
    await db.leads.create_index("intent_category")
    await db.leads.create_index("project")
    await db.leads.create_index("is_vip")
    await db.leads.create_index([("updated_at", -1)])   # default sort

    # Lead — compound: most common filter combos + sort
    await db.leads.create_index([("budget_category", 1), ("updated_at", -1)])
    await db.leads.create_index([("temperature", 1), ("updated_at", -1)])
    await db.leads.create_index([("location_category", 1), ("updated_at", -1)])
    await db.leads.create_index([("is_vip", 1), ("updated_at", -1)])

    # Lead — full-text search
    await db.leads.create_index(
        [("full_name", "text"), ("mobile", "text"), ("project", "text")]
    )

    # Call history indexes
    await db.call_history.create_index("id", unique=True)
    await db.call_history.create_index("mobile_digits")
    await db.call_history.create_index("lead_id")
    await db.call_history.create_index("campaign_id")
    await db.call_history.create_index("campaign")
    await db.call_history.create_index([("created_at", -1)])

    # Upload audit trail (Campaign page)
    await db.lead_upload_history.create_index([("created_at", -1)])
    await db.lead_upload_failures.create_index("upload_id")
    await db.campaigns.create_index("futwork_campaign_id")

    logger.info("Database indexes initialized")
