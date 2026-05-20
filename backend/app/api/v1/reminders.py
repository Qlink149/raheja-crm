import json
import logging
import re
import uuid
from datetime import timedelta
from typing import List

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...constants.lead_kpi import RNR_STATUS_REGEX
from ...core.config import settings
from ...core.database import get_db
from ...core.security import get_current_user
from ...core.time_utils import iso_utc_now, utc_now
from ...services.notification_service import create_notification
from ...utils.users import resolve_user_id_by_full_name

logger = logging.getLogger(__name__)
router = APIRouter()

REMINDER_TEMPLATES = {
    "followup": "clara_reminder_1",
    "task_due": "clara_task_reminder",
}


def _lead_status_field_query(statuses: List[str]) -> dict:
    if not statuses:
        return {}
    return {
        "$or": [
            {"status": {"$in": statuses}},
            {"lead_status": {"$in": statuses}},
        ]
    }


def _rep_on_lead(lead: dict) -> str:
    return (
        lead.get("assigned_to")
        or lead.get("assigned_to_name")
        or ""
    )


async def send_whatsapp_template(destination: str, template_name: str, params: List[str]):
    if not settings.GUPSHUP_API_KEY or not settings.GUPSHUP_SOURCE_PHONE:
        logger.debug("Gupshup not configured; skipping WhatsApp send")
        return None
    try:
        destination = re.sub(r"[^0-9]", "", destination)
        if len(destination) == 10:
            destination = "91" + destination

        template_data = {"id": template_name, "params": params}
        data = {
            "source": settings.GUPSHUP_SOURCE_PHONE,
            "destination": destination,
            "template": json.dumps(template_data),
        }

        async with httpx.AsyncClient() as client_http:
            resp = await client_http.post(
                f"{settings.GUPSHUP_BASE_URL}/wa/api/v1/template/msg",
                headers={
                    "apikey": settings.GUPSHUP_API_KEY,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data=data,
                timeout=30.0,
            )
            ct = resp.headers.get("content-type", "")
            result = (
                resp.json()
                if ct.startswith("application/json")
                else {"raw": resp.text}
            )
            logger.info("WhatsApp template sent to %s: %s", destination, result)
            return result
    except Exception as e:
        logger.error("Failed to send WhatsApp template to %s: %s", destination, e)
        return None


async def seed_default_reminder_rules(db):
    rules = [
        {
            "id": str(uuid.uuid4()),
            "name": "Follow-up Due (2 days)",
            "trigger": "followup_due",
            "days_threshold": 2,
            "is_active": True,
            "send_whatsapp": True,
            "lead_statuses": ["Follow Up 1", "Follow Up 2"],
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Site Visit Tomorrow",
            "trigger": "site_visit_tomorrow",
            "days_threshold": 0,
            "is_active": True,
            "send_whatsapp": True,
            "lead_statuses": ["Site Visit Scheduled"],
        },
        {
            "id": str(uuid.uuid4()),
            "name": "RNR Stale (3 days)",
            "trigger": "rnr_stale",
            "days_threshold": 3,
            "is_active": True,
            "send_whatsapp": False,
            "lead_statuses": ["RNR"],
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Task Overdue",
            "trigger": "task_overdue",
            "days_threshold": 0,
            "is_active": True,
            "send_whatsapp": True,
            "lead_statuses": [],
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Cold Lead Reactivation (7 days)",
            "trigger": "followup_due",
            "days_threshold": 7,
            "is_active": True,
            "send_whatsapp": False,
            "lead_statuses": ["Gone Cold"],
        },
    ]
    for rule in rules:
        rule["created_at"] = iso_utc_now()
        rule["created_at_dt"] = utc_now()
        await db.reminder_rules.insert_one(rule)
    logger.info("Seeded %s default reminder rules", len(rules))
    return rules


async def process_reminders(db) -> int:
    try:
        now_dt = utc_now()
        now_iso = iso_utc_now()
        today = now_dt.strftime("%Y-%m-%d")

        rules = await db.reminder_rules.find({"is_active": True}, {"_id": 0}).to_list(50)
        if not rules:
            rules = await seed_default_reminder_rules(db)

        users = await db.users.find(
            {}, {"_id": 0, "email": 1, "full_name": 1, "phone": 1}
        ).to_list(100)
        user_phones = {u["full_name"]: u.get("phone", "") for u in users}

        reminders_created = 0

        for rule in rules:
            if not rule.get("is_active", True):
                continue

            trigger = rule["trigger"]
            days = rule.get("days_threshold", 0)

            if trigger == "followup_due":
                cutoff = (now_dt - timedelta(days=days)).isoformat()
                status_q = _lead_status_field_query(rule.get("lead_statuses") or [])
                lead_query = {
                    "$and": [
                        status_q or {"status": {"$regex": "Follow Up", "$options": "i"}},
                        {
                            "$or": [
                                {"updated_at": {"$lt": cutoff}},
                                {"updated_at": {"$exists": False}},
                            ]
                        },
                    ]
                }
                if not status_q:
                    lead_query["$and"][0] = {
                        "$or": [
                            {"status": {"$regex": "Follow Up", "$options": "i"}},
                            {"lead_status": {"$regex": "Follow Up", "$options": "i"}},
                        ]
                    }

                leads = await db.leads.find(lead_query, {"_id": 0}).to_list(200)
                for lead in leads:
                    dedupe_key = f"reminder:{trigger}:{lead['id']}:{today}"
                    if await db.reminders.find_one({"dedupe_key": dedupe_key}):
                        continue

                    rep = _rep_on_lead(lead)
                    lead_name = (
                        lead.get("full_name")
                        or f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
                    )
                    project = lead.get("project", "N/A")
                    rep_user_id = await resolve_user_id_by_full_name(db, rep)
                    status_label = lead.get("status") or lead.get("lead_status") or "Follow Up"

                    reminder_doc = {
                        "id": str(uuid.uuid4()),
                        "lead_id": lead["id"],
                        "lead_name": lead_name,
                        "assigned_to": rep,
                        "assigned_user_id": rep_user_id,
                        "trigger": trigger,
                        "rule_name": rule["name"],
                        "message": f"Follow up reminder: {lead_name} ({project}) is in {status_label} status for {days}+ days",
                        "status": "sent",
                        "whatsapp_sent": False,
                        "created_at": now_iso,
                        "created_at_dt": now_dt,
                        "dedupe_key": dedupe_key,
                    }

                    phone = user_phones.get(rep, "")
                    if rule.get("send_whatsapp", True) and phone:
                        result = await send_whatsapp_template(
                            phone,
                            REMINDER_TEMPLATES.get("followup", ""),
                            [
                                rep.split()[0] if rep else "Team",
                                lead_name,
                                project,
                                status_label,
                            ],
                        )
                        if result:
                            reminder_doc["whatsapp_sent"] = True

                    if rep_user_id:
                        await create_notification(
                            db,
                            type="reminder",
                            title="Follow-up Reminder",
                            message=reminder_doc["message"],
                            lead_id=lead["id"],
                            lead_name=lead_name,
                            recipient_user_id=rep_user_id,
                            recipient_name=rep,
                            assigned_to=rep,
                            urgency="action_needed",
                            dedupe_key=f"notification:reminder:{trigger}:{lead['id']}:{today}",
                        )

                    await db.reminders.insert_one(reminder_doc)
                    reminders_created += 1

            elif trigger == "site_visit_tomorrow":
                leads = await db.leads.find(
                    {
                        "$or": [
                            {"status": {"$regex": "Site Visit Scheduled", "$options": "i"}},
                            {"lead_status": {"$regex": "Site Visit Scheduled", "$options": "i"}},
                        ]
                    },
                    {"_id": 0},
                ).to_list(200)
                for lead in leads:
                    dedupe_key = f"reminder:{trigger}:{lead['id']}:{today}"
                    if await db.reminders.find_one({"dedupe_key": dedupe_key}):
                        continue

                    rep = _rep_on_lead(lead)
                    lead_name = (
                        lead.get("full_name")
                        or f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
                    )
                    project = lead.get("project", "N/A")
                    rep_user_id = await resolve_user_id_by_full_name(db, rep)

                    reminder_doc = {
                        "id": str(uuid.uuid4()),
                        "lead_id": lead["id"],
                        "lead_name": lead_name,
                        "assigned_to": rep,
                        "assigned_user_id": rep_user_id,
                        "trigger": trigger,
                        "rule_name": rule["name"],
                        "message": f"Site visit reminder: {lead_name} has a site visit scheduled for {project}",
                        "status": "sent",
                        "whatsapp_sent": False,
                        "created_at": now_iso,
                        "created_at_dt": now_dt,
                        "dedupe_key": dedupe_key,
                    }

                    phone = user_phones.get(rep, "")
                    if rule.get("send_whatsapp", True) and phone:
                        result = await send_whatsapp_template(
                            phone,
                            REMINDER_TEMPLATES.get("followup", ""),
                            [
                                rep.split()[0] if rep else "Team",
                                lead_name,
                                project,
                                "Site Visit Scheduled",
                            ],
                        )
                        if result:
                            reminder_doc["whatsapp_sent"] = True

                    if rep_user_id:
                        await create_notification(
                            db,
                            type="reminder",
                            title="Site Visit Reminder",
                            message=reminder_doc["message"],
                            lead_id=lead["id"],
                            lead_name=lead_name,
                            recipient_user_id=rep_user_id,
                            recipient_name=rep,
                            assigned_to=rep,
                            urgency="action_needed",
                            dedupe_key=f"notification:reminder:{trigger}:{lead['id']}:{today}",
                        )

                    await db.reminders.insert_one(reminder_doc)
                    reminders_created += 1

            elif trigger == "rnr_stale":
                cutoff = (now_dt - timedelta(days=days)).isoformat()
                leads = await db.leads.find(
                    {
                        "$and": [
                            {
                                "$or": [
                                    {"status": {"$regex": RNR_STATUS_REGEX}},
                                    {"lead_status": {"$regex": RNR_STATUS_REGEX}},
                                    {"is_rnr": True},
                                ]
                            },
                            {
                                "$or": [
                                    {"updated_at": {"$lt": cutoff}},
                                    {"updated_at": {"$exists": False}},
                                ]
                            },
                        ]
                    },
                    {"_id": 0},
                ).to_list(200)
                for lead in leads:
                    dedupe_key = f"reminder:{trigger}:{lead['id']}:{today}"
                    if await db.reminders.find_one({"dedupe_key": dedupe_key}):
                        continue

                    rep = _rep_on_lead(lead)
                    lead_name = (
                        lead.get("full_name")
                        or f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
                    )
                    rep_user_id = await resolve_user_id_by_full_name(db, rep)

                    reminder_doc = {
                        "id": str(uuid.uuid4()),
                        "lead_id": lead["id"],
                        "lead_name": lead_name,
                        "assigned_to": rep,
                        "assigned_user_id": rep_user_id,
                        "trigger": trigger,
                        "rule_name": rule["name"],
                        "message": f"RNR Alert: {lead_name} has been unreachable for {days}+ days. Consider reassignment.",
                        "status": "sent",
                        "whatsapp_sent": False,
                        "created_at": now_iso,
                        "created_at_dt": now_dt,
                        "dedupe_key": dedupe_key,
                    }

                    if rep_user_id:
                        await create_notification(
                            db,
                            type="reminder",
                            title="RNR Alert",
                            message=reminder_doc["message"],
                            lead_id=lead["id"],
                            lead_name=lead_name,
                            recipient_user_id=rep_user_id,
                            recipient_name=rep,
                            assigned_to=rep,
                            severity="high",
                            urgency="critical",
                            dedupe_key=f"notification:reminder:{trigger}:{lead['id']}:{today}",
                        )

                    await db.reminders.insert_one(reminder_doc)
                    reminders_created += 1

            elif trigger == "task_overdue":
                overdue_tasks = await db.tasks.find(
                    {"status": "pending", "due_date": {"$lt": today}},
                    {"_id": 0},
                ).to_list(200)
                for task in overdue_tasks:
                    dedupe_key = f"reminder:{trigger}:{task['id']}:{today}"
                    if await db.reminders.find_one({"dedupe_key": dedupe_key}):
                        continue

                    rep = task.get("assigned_to", "")
                    rep_user_id = task.get("assigned_user_id") or await resolve_user_id_by_full_name(
                        db, rep
                    )

                    reminder_doc = {
                        "id": str(uuid.uuid4()),
                        "task_id": task["id"],
                        "lead_id": task.get("lead_id", ""),
                        "lead_name": task.get("lead_name", ""),
                        "assigned_to": rep,
                        "assigned_user_id": rep_user_id,
                        "trigger": trigger,
                        "rule_name": rule["name"],
                        "message": f"Overdue task: '{task.get('description', '')}' was due on {task.get('due_date', '')}",
                        "status": "sent",
                        "whatsapp_sent": False,
                        "created_at": now_iso,
                        "created_at_dt": now_dt,
                        "dedupe_key": dedupe_key,
                    }

                    phone = user_phones.get(rep, "")
                    if rule.get("send_whatsapp", True) and phone:
                        result = await send_whatsapp_template(
                            phone,
                            REMINDER_TEMPLATES.get("task_due", ""),
                            [
                                rep.split()[0] if rep else "Team",
                                task.get("description", "")[:50],
                                task.get("due_date", "today"),
                                task.get("priority", "medium"),
                            ],
                        )
                        if result:
                            reminder_doc["whatsapp_sent"] = True

                    if rep_user_id:
                        await create_notification(
                            db,
                            type="reminder",
                            title="Overdue Task",
                            message=reminder_doc["message"],
                            lead_id=task.get("lead_id", ""),
                            lead_name=task.get("lead_name", ""),
                            recipient_user_id=rep_user_id,
                            recipient_name=rep,
                            assigned_to=rep,
                            severity="high",
                            urgency="critical",
                            dedupe_key=f"notification:reminder:{trigger}:{task['id']}:{today}",
                        )

                    await db.reminders.insert_one(reminder_doc)
                    reminders_created += 1

        logger.info("Reminder engine: created %s reminders", reminders_created)
        return reminders_created
    except Exception as e:
        logger.error("Reminder engine error: %s", e)
        return 0


class ManualReminderRequest(BaseModel):
    lead_id: str
    message: str
    send_whatsapp: bool = False


@router.get("/reminders/rules")
async def get_reminder_rules(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    rules = await db.reminder_rules.find({}, {"_id": 0}).to_list(50)
    if not rules:
        rules = await seed_default_reminder_rules(db)
    return rules


@router.put("/reminders/rules/{rule_id}")
async def update_reminder_rule(
    rule_id: str,
    updates: dict,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    allowed = {"is_active", "send_whatsapp", "days_threshold", "name"}
    update_data = {k: v for k, v in updates.items() if k in allowed}
    await db.reminder_rules.update_one({"id": rule_id}, {"$set": update_data})
    return {"message": "Rule updated"}


@router.get("/reminders/history")
async def get_reminder_history(
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    reminders = await db.reminders.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return reminders


@router.post("/reminders/trigger")
async def trigger_reminders_now(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    count = await process_reminders(db)
    return {"message": f"Reminder engine ran. Created {count} reminders."}


@router.post("/reminders/send")
async def send_manual_reminder(
    req: ManualReminderRequest,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    lead = await db.leads.find_one({"id": req.lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead_name = (
        lead.get("full_name")
        or f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
    )
    rep = _rep_on_lead(lead)
    rep_user_id = await resolve_user_id_by_full_name(db, rep)
    now_dt = utc_now()
    now_iso = iso_utc_now()
    dedupe_key = f"reminder:manual:{req.lead_id}:{now_iso}"

    reminder_doc = {
        "id": str(uuid.uuid4()),
        "lead_id": req.lead_id,
        "lead_name": lead_name,
        "assigned_to": rep,
        "assigned_user_id": rep_user_id,
        "trigger": "manual",
        "rule_name": "Manual Reminder",
        "message": req.message,
        "status": "sent",
        "whatsapp_sent": False,
        "created_at": now_iso,
        "created_at_dt": now_dt,
        "dedupe_key": dedupe_key,
    }

    if req.send_whatsapp and rep:
        users = await db.users.find({"full_name": rep}, {"_id": 0}).to_list(1)
        phone = users[0].get("phone", "") if users else ""
        if phone:
            result = await send_whatsapp_template(
                phone,
                REMINDER_TEMPLATES.get("followup", ""),
                [
                    rep.split()[0] if rep else "Team",
                    lead_name,
                    lead.get("project", "N/A"),
                    lead.get("status") or lead.get("lead_status") or "Open",
                ],
            )
            if result:
                reminder_doc["whatsapp_sent"] = True

    if rep_user_id:
        await create_notification(
            db,
            type="reminder",
            title="Manual Reminder",
            message=req.message,
            lead_id=req.lead_id,
            lead_name=lead_name,
            recipient_user_id=rep_user_id,
            recipient_name=rep,
            assigned_to=rep,
            urgency="action_needed",
            dedupe_key=f"notification:reminder:manual:{req.lead_id}:{now_iso}",
        )

    await db.reminders.insert_one(reminder_doc)
    return {
        "message": "Reminder sent",
        "id": reminder_doc["id"],
        "whatsapp_sent": reminder_doc["whatsapp_sent"],
    }
