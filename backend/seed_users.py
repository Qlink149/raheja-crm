"""Ensure the single Raheja admin user exists."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.core.security import hash_password

ADMIN_EMAIL = "it@krahejarealty.com"
ADMIN_PASSWORD = "Kraheja@123"
ADMIN_NAME = "utpal"
ADMIN_ROLE = "admin"


def _build_admin_doc(user_id: Optional[str] = None) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "id": user_id or str(uuid.uuid4()),
        "email": ADMIN_EMAIL,
        "full_name": ADMIN_NAME,
        "role": ADMIN_ROLE,
        "hashed_password": hash_password(ADMIN_PASSWORD),
        "is_active": True,
        "current_session_id": None,
        "notification_dismissals": [],
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }


async def ensure_admin_user(db) -> int:
    """Create or update the admin user. Returns 1 if inserted, 0 if updated."""
    existing = await db.users.find_one({"email": ADMIN_EMAIL})
    now = datetime.now(timezone.utc).isoformat()
    if existing:
        await db.users.update_one(
            {"email": ADMIN_EMAIL},
            {
                "$set": {
                    "full_name": ADMIN_NAME,
                    "role": ADMIN_ROLE,
                    "hashed_password": hash_password(ADMIN_PASSWORD),
                    "is_active": True,
                    "updated_at": now,
                }
            },
        )
        return 0

    await db.users.insert_one(_build_admin_doc())
    return 1


async def reset_to_single_admin(db) -> int:
    """Delete all users and insert only the admin user. Returns deleted count."""
    deleted = (await db.users.delete_many({})).deleted_count
    await db.users.insert_one(_build_admin_doc())
    return deleted


async def seed_users(db) -> int:
    return await ensure_admin_user(db)
