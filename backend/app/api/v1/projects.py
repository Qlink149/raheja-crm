from fastapi import APIRouter, Depends
from typing import List, Dict, Any
from ...core.database import get_db

router = APIRouter()

@router.get("")
async def get_projects(db = Depends(get_db)):
    pipeline = [
        {"$group": {"_id": "$project", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 15},
        {"$project": {"name": "$_id", "count": 1, "_id": 0}}
    ]
    # Filter out empty or placeholder projects
    projects = await db.leads.aggregate(pipeline).to_list(length=15)
    return [p for p in projects if p.get("name") and p.get("name") != "Profiling in Progress"]
