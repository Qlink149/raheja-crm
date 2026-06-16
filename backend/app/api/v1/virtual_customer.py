from fastapi import APIRouter, Depends

from ...core.database import get_db
from ...core.preview_access import fetch_preview_payload, is_vc_preview_tier
from ...core.security import get_current_user
from ...models.lead_preview import VirtualCustomerPreviewResponse

router = APIRouter()


@router.get("/preview", response_model=VirtualCustomerPreviewResponse)
async def get_virtual_customer_preview(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    if not is_vc_preview_tier():
        from fastapi import HTTPException

        raise HTTPException(
            status_code=403,
            detail="Preview endpoint is only available in preview tier.",
        )
    payload = await fetch_preview_payload(db, current_user)
    return payload
