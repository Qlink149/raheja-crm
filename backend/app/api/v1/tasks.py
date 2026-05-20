import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...core.database import get_db
from ...core.security import get_current_user
from ...core.time_utils import iso_utc_now, utc_now
from ...services.notification_service import create_notification, _lead_display_name
from ...utils.users import resolve_user_id_by_full_name

router = APIRouter()


class TaskCreate(BaseModel):
    description: str
    due_date: str
    due_time: Optional[str] = None
    priority: str = "medium"
    reminder_method: str = "email"
    assigned_to: Optional[str] = None
    assigned_user_id: Optional[str] = None


class StandaloneTaskCreate(BaseModel):
    description: str
    due_date: str
    due_time: Optional[str] = None
    priority: str = "medium"
    lead_id: Optional[str] = None
    lead_name: Optional[str] = None
    assigned_user_id: Optional[str] = None


class TaskUpdatePatch(BaseModel):
    description: Optional[str] = None
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    priority: Optional[str] = None
    reminder_method: Optional[str] = None
    assigned_to: Optional[str] = None
    assigned_user_id: Optional[str] = None
    status: Optional[str] = None


@router.post("/leads/{lead_id}/tasks")
async def add_task(
    lead_id: str,
    task: TaskCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    task_id = str(uuid.uuid4())
    assigned = (
        task.assigned_to
        or lead.get("assigned_to")
        or lead.get("assigned_to_name")
        or current_user["full_name"]
    )
    assigned_user_id = task.assigned_user_id or await resolve_user_id_by_full_name(db, assigned)
    if not assigned_user_id:
        assigned_user_id = lead.get("assigned_user_id") or current_user.get("id")
    if not assigned_user_id:
        raise HTTPException(status_code=400, detail="assigned_user_id is required")

    now_dt = utc_now()
    now_iso = iso_utc_now()
    due_at = datetime.fromisoformat(
        f"{task.due_date}T{task.due_time or '09:00'}:00"
    ).replace(tzinfo=timezone.utc)

    task_doc = {
        "id": task_id,
        "lead_id": lead_id,
        "description": task.description,
        "due_date": task.due_date,
        "due_time": task.due_time,
        "due_at_dt": due_at,
        "priority": task.priority,
        "reminder_method": task.reminder_method,
        "assigned_to": assigned,
        "assigned_to_name": assigned,
        "assigned_user_id": assigned_user_id,
        "status": "pending",
        "created_by": current_user["full_name"],
        "created_by_user_id": current_user.get("id"),
        "created_at": now_iso,
        "created_at_dt": now_dt,
    }
    await db.tasks.insert_one(task_doc)

    due_str = task.due_date
    if task.due_time:
        due_str += f" at {task.due_time}"

    lead_name = _lead_display_name(lead)
    severity = (
        "high"
        if task.priority == "high"
        else "medium"
        if task.priority == "medium"
        else "low"
    )
    await create_notification(
        db,
        type="task_reminder",
        title=f"Task: {task.description[:50]}",
        message=f"Due {due_str} for {lead_name}",
        lead_id=lead_id,
        lead_name=lead_name,
        recipient_user_id=assigned_user_id,
        recipient_name=assigned,
        assigned_to=assigned,
        severity=severity,
        urgency="action_needed",
        task_id=task_id,
        extra_fields={"due_at": f"{task.due_date}T{task.due_time or '09:00'}:00"},
    )

    return {"message": "Task created", "task_id": task_id}


@router.post("/tasks")
async def create_standalone_task(
    task: StandaloneTaskCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    task_id = str(uuid.uuid4())
    assigned_user_id = task.assigned_user_id or current_user.get("id")
    if not assigned_user_id:
        raise HTTPException(status_code=400, detail="assigned_user_id is required")

    now_dt = utc_now()
    now_iso = iso_utc_now()
    lead_name = task.lead_name or ""

    if task.lead_id:
        lead = await db.leads.find_one({"id": task.lead_id}, {"_id": 0})
        if lead:
            lead_name = _lead_display_name(lead)

    due_at = datetime.fromisoformat(
        f"{task.due_date}T{task.due_time or '09:00'}:00"
    ).replace(tzinfo=timezone.utc)

    task_doc = {
        "id": task_id,
        "lead_id": task.lead_id or "",
        "lead_name": lead_name,
        "description": task.description,
        "due_date": task.due_date,
        "due_time": task.due_time,
        "due_at_dt": due_at,
        "priority": task.priority,
        "reminder_method": "email",
        "assigned_to": current_user["full_name"],
        "assigned_to_name": current_user["full_name"],
        "assigned_user_id": assigned_user_id,
        "status": "pending",
        "created_by": current_user["full_name"],
        "created_by_user_id": current_user.get("id"),
        "created_at": now_iso,
        "created_at_dt": now_dt,
    }
    await db.tasks.insert_one(task_doc)
    return {"message": "Task created", "task_id": task_id}


@router.get("/tasks")
async def get_tasks(
    current_user: dict = Depends(get_current_user),
    status: Optional[str] = None,
    lead_id: Optional[str] = None,
    db=Depends(get_db),
):
    query: dict = {}
    if status:
        query["status"] = status
    if lead_id:
        query["lead_id"] = lead_id
    role = (current_user.get("role") or "sales").lower()
    if role != "admin":
        query["assigned_user_id"] = current_user["id"]
    tasks = await db.tasks.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    return tasks


@router.put("/tasks/{task_id}")
async def update_task(
    task_id: str,
    update: TaskUpdatePatch,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    task_doc = await db.tasks.find_one({"id": task_id}, {"_id": 0})
    if not task_doc:
        raise HTTPException(status_code=404, detail="Task not found")

    patch = update.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(status_code=400, detail="No fields to update")

    if "status" in patch and patch["status"] not in {
        "pending",
        "done",
        "completed",
        "cancelled",
    }:
        raise HTTPException(status_code=400, detail="Invalid status")

    now_dt = utc_now()
    now_iso = iso_utc_now()
    patch["updated_at"] = now_iso
    patch["updated_at_dt"] = now_dt
    await db.tasks.update_one({"id": task_id}, {"$set": patch})
    return {"message": "Task updated"}
