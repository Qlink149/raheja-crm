from fastapi import APIRouter, Depends, HTTPException, Query
from ...core.database import get_db
from ...services.ai_service import AIService

router = APIRouter()

@router.post("/leads/{lead_id}/persona-summary")
async def get_persona(lead_id: str, refresh: bool = Query(False), db = Depends(get_db)):
    service = AIService(db)
    try:
        persona = await service.generate_persona(lead_id, refresh=refresh)
        return {"summary": persona}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/leads/{lead_id}/strategic-next-move")
async def get_strategic_move(lead_id: str, refresh: bool = Query(False), db = Depends(get_db)):
    service = AIService(db)
    try:
        move = await service.generate_strategic_move(lead_id, refresh=refresh)
        # Return 'recommendation' key — that's what CustomerDetailPage.jsx expects
        return {"recommendation": move}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/leads/{lead_id}/call-summary")
async def get_call_summary(lead_id: str, refresh: bool = Query(False), db = Depends(get_db)):
    service = AIService(db)
    try:
        summary = await service.generate_call_summary(lead_id, refresh=refresh)
        return {"summary": summary}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
