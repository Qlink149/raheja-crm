from typing import Callable

from fastapi import Depends, HTTPException, status

from .security import get_current_user

ROLE_ADMIN = "admin"
ROLE_SALES = "sales"


def require_roles(*roles: str) -> Callable:
    allowed = {r.lower() for r in roles}

    async def _dep(current_user: dict = Depends(get_current_user)) -> dict:
        role = (current_user.get("role") or ROLE_SALES).lower()
        if role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return _dep


require_admin = require_roles(ROLE_ADMIN)
