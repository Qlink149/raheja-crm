import uuid
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from ...core.config import settings
from ...core.database import get_db
from ...core.security import (
    create_access_token,
    create_refresh_token,
    get_current_user,
    get_time_greeting,
    hash_password,
    verify_password,
)
from ...models.user import RefreshTokenRequest, Token, UserCreate, UserResponse

router = APIRouter()


@router.post("/register", response_model=UserResponse)
async def register(user_data: UserCreate, db=Depends(get_db)):
    existing = await db.users.find_one({"email": user_data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc)
    role = user_data.role if user_data.role in ("admin", "sales") else "sales"
    user_doc = {
        "id": user_id,
        "email": user_data.email,
        "full_name": user_data.full_name,
        "role": role,
        "hashed_password": hash_password(user_data.password),
        "is_active": True,
        "current_session_id": None,
        "created_at": created_at.isoformat(),
        "updated_at": created_at.isoformat(),
    }
    await db.users.insert_one(user_doc)
    return UserResponse(
        id=user_id,
        email=user_data.email,
        full_name=user_data.full_name,
        role=role,
        is_active=True,
        created_at=created_at,
    )


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db=Depends(get_db)):
    user = await db.users.find_one({"email": form_data.username}, {"_id": 0})
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    sid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"current_session_id": sid, "updated_at": now}},
    )

    access_token = create_access_token(data={"sub": user["id"], "sid": sid})
    refresh_token = create_refresh_token(data={"sub": user["id"], "sid": sid})
    role = user.get("role") or "sales"

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user={
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": role,
        },
    )


@router.post("/refresh")
async def refresh_token(body: RefreshTokenRequest, db=Depends(get_db)):
    try:
        payload = jwt.decode(
            body.refresh_token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")

        user_id = payload.get("sub")
        token_sid = payload.get("sid")
        user = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        db_sid = user.get("current_session_id")
        if db_sid and token_sid != db_sid:
            raise HTTPException(
                status_code=401,
                detail="Session invalidated. Please log in again.",
            )

        new_access_token = create_access_token(
            data={"sub": user_id, "sid": token_sid or db_sid}
        )
        return {"access_token": new_access_token, "token_type": "bearer"}
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user), db=Depends(get_db)):
    now = datetime.now(timezone.utc).isoformat()
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": {"current_session_id": None, "updated_at": now}},
    )
    return {"success": True}


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    first_name = (current_user.get("full_name") or "User").split()[0]
    role = current_user.get("role") or "sales"
    return {
        "id": current_user["id"],
        "email": current_user["email"],
        "full_name": current_user["full_name"],
        "role": role,
        "greeting": f"{get_time_greeting()}, {first_name}",
    }
