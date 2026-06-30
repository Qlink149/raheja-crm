"""One-shot: remove all users and create the single admin account."""
import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import close_mongo_connection, connect_to_mongo, db_instance
from seed_users import ADMIN_EMAIL, reset_to_single_admin


async def main() -> None:
    await connect_to_mongo()
    try:
        deleted = await reset_to_single_admin(db_instance.db)
        print(f"Removed {deleted} user(s). Created admin: {ADMIN_EMAIL}")
    finally:
        await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(main())
