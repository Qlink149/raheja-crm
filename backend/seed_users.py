"""
Config-driven user seeder for Rustomjee CRM.

Usage (from backend/):
  python seed_users.py
  python seed_users.py --reset-password
  SEED_USERS_FILE=./custom_users.json python seed_users.py
"""
from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

DEFAULT_JSON = Path(__file__).resolve().parent / "seed_users.json"
NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def _user_id(email: str) -> str:
    return str(uuid.uuid5(NAMESPACE, email.strip().lower()))


def load_seed_config(path: Path) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


async def seed_users(
    db,
    *,
    config_path: Path | None = None,
    reset_password: bool = False,
) -> int:
    from app.core.security import hash_password

    path = config_path or Path(os.getenv("SEED_USERS_FILE", str(DEFAULT_JSON)))
    cfg = load_seed_config(path)
    pwd_env = cfg.get("default_password_env") or "SEED_DEFAULT_PASSWORD"
    plain = os.getenv(pwd_env, "rustomjee@123")
    hashed = hash_password(plain)
    users: List[Dict[str, Any]] = cfg.get("users") or []
    now = datetime.now(timezone.utc).isoformat()
    count = 0

    for u in users:
        email = (u.get("email") or "").strip().lower()
        if not email:
            continue
        role = (u.get("role") or "sales").strip().lower()
        if role not in ("admin", "sales"):
            role = "sales"
        full_name = (u.get("full_name") or email.split("@")[0]).strip()
        uid = _user_id(email)
        existing = await db.users.find_one({"email": email})
        if not existing:
            doc = {
                "id": uid,
                "email": email,
                "full_name": full_name,
                "role": role,
                "hashed_password": hashed,
                "is_active": True,
                "current_session_id": None,
                "created_at": now,
                "updated_at": now,
            }
            await db.users.insert_one(doc)
            count += 1
        else:
            sets: Dict[str, Any] = {
                "role": role,
                "full_name": full_name,
                "updated_at": now,
            }
            if reset_password:
                sets["hashed_password"] = hashed
            if not existing.get("role"):
                sets["role"] = role
            await db.users.update_one({"email": email}, {"$set": sets})
    return count


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed CRM users from JSON")
    parser.add_argument("--reset-password", action="store_true")
    parser.add_argument("--config", type=str, default="")
    args = parser.parse_args()

    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.getenv("DB_NAME", "rustomjee_crm")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    cfg_path = Path(args.config) if args.config else None
    n = await seed_users(db, config_path=cfg_path, reset_password=args.reset_password)
    print(f"Seeded/updated users ({n} new).")
    client.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
