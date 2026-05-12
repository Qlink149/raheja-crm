from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from ...core.database import get_db
from ...services.structured_ai_service import StructuredAIService

router = APIRouter()

@router.post("/leads/{lead_id}/persona-summary")
async def get_persona(lead_id: str, refresh: bool = Query(False), db = Depends(get_db)):
    service = StructuredAIService(db)
    try:
        persona = await service.generate_persona(lead_id, refresh=refresh)
        return {"summary": persona}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/leads/{lead_id}/strategic-next-move")
async def get_strategic_move(lead_id: str, refresh: bool = Query(False), db = Depends(get_db)):
    service = StructuredAIService(db)
    try:
        move = await service.generate_strategic_move(lead_id, refresh=refresh)
        # Return 'recommendation' key — that's what CustomerDetailPage.jsx expects
        return {"recommendation": move}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/leads/{lead_id}/call-summary")
async def get_call_summary(
    lead_id: str,
    refresh: bool = Query(False),
    call_sid: Optional[str] = Query(None),
    db=Depends(get_db),
):
    service = StructuredAIService(db)
    try:
        summary = await service.generate_call_summary_unified(
            lead_id, call_sid=call_sid, refresh=refresh
        )
        return {"summary": summary}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
