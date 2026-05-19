from fastapi import APIRouter, Depends

from ...core.database import get_db
from ...core.rbac import require_admin
from ...services.assignment_service import AssignmentService

router = APIRouter()


@router.get("/sales-reps")
async def list_sales_reps(
    _admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    service = AssignmentService(db)
    return await service.list_sales_reps()
