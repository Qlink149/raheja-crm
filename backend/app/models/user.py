from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr

UserRole = Literal["admin", "sales"]


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: UserRole = "sales"


class UserResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    email: EmailStr
    full_name: str
    role: UserRole = "sales"
    is_active: bool = True
    created_at: Optional[datetime] = None


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class RefreshTokenRequest(BaseModel):
    refresh_token: str
