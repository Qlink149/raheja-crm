"""User lookup helpers."""
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase


async def resolve_user_id_by_full_name(
    db: AsyncIOMotorDatabase, full_name: str
) -> Optional[str]:
    if not full_name or not str(full_name).strip():
        return None
    user = await db.users.find_one(
        {"full_name": str(full_name).strip()},
        {"_id": 0, "id": 1},
    )
    return user.get("id") if user else None
