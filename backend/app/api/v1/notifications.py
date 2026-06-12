from datetime import datetime, timedelta

from typing import Any, Dict, List, Optional



from fastapi import APIRouter, Depends



from ...constants.lead_kpi import RNR_STATUS_REGEX

from ...core.database import get_db

from ...core.security import get_current_user

from ...core.time_utils import iso_utc_now, utc_now

from ...services.assignment_service import rep_lead_filter
from ...services.notification_service import sanitize_notification_text



router = APIRouter()



_MAX_DISMISSALS = 4000

_HIGH_INTENT_DISPOSITIONS = ("Hot Lead", "Semi-Interested")

_INTENT_TRANSCRIPT_REGEX = r"(?i)(interested|site\s*visit|budget|book|visit|buy|purchase)"





def _parse_ts(val: Any, fallback: datetime) -> datetime:

    if isinstance(val, datetime):

        return val if val.tzinfo else val.replace(tzinfo=fallback.tzinfo)

    if isinstance(val, str):

        try:

            return datetime.fromisoformat(val.replace("Z", "+00:00"))

        except ValueError:

            return fallback

    return fallback





def _stored_notifications_query(current_user: dict) -> Dict[str, Any]:

    role = (current_user.get("role") or "sales").lower()

    if role == "admin":

        return {}

    uid = current_user["id"]

    return {

        "$or": [

            {"recipient_user_id": uid},

            {"recipient_user_id": {"$exists": False}},

            {"recipient_user_id": None},

            {"recipient_user_id": ""},

        ]

    }





def _scope_filter(current_user: dict) -> Optional[Dict[str, Any]]:

    role = (current_user.get("role") or "sales").lower()

    if role == "admin":

        return None

    return rep_lead_filter(

        current_user["id"],

        current_user.get("full_name") or "",

    )





def _merge_scope(base: Dict[str, Any], scope: Optional[Dict[str, Any]]) -> Dict[str, Any]:

    if not scope:

        return base

    return {"$and": [base, scope]}


def _unread_filter() -> Dict[str, Any]:
    return {
        "$or": [
            {"is_read": False},
            {"is_read": {"$exists": False}},
            {"is_read": None},
        ]
    }


def _recipient_scope_filter(current_user: dict) -> List[Dict[str, Any]]:
    return [
        {"recipient_user_id": current_user["id"]},
        {"recipient_user_id": {"$exists": False}},
        {"recipient_user_id": None},
        {"recipient_user_id": ""},
    ]





async def _build_auto_notifications(

    db, current_user: Optional[dict] = None

) -> List[Dict[str, Any]]:

    auto: List[Dict[str, Any]] = []

    now_dt = utc_now()

    now_iso = iso_utc_now()

    today = now_dt.strftime("%Y-%m-%d")

    scope = _scope_filter(current_user) if current_user else None



    task_base: Dict[str, Any] = {"status": "pending", "due_date": {"$lt": today}}
    if scope and current_user:
        scoped_leads = await db.leads.find(scope, {"_id": 0, "id": 1}).to_list(5000)
        lead_ids = [l["id"] for l in scoped_leads if l.get("id")]
        task_or: List[Dict[str, Any]] = [{"assigned_user_id": current_user["id"]}]
        if lead_ids:
            task_or.append({"lead_id": {"$in": lead_ids}})
        task_query = {"$and": [task_base, {"$or": task_or}]}
    else:
        task_query = task_base
    overdue_tasks = await db.tasks.find(task_query, {"_id": 0}).to_list(50)

    for task in overdue_tasks:

        auto.append(

            {

                "id": f"auto-task-{task.get('id', '')}",

                "type": "task_overdue",

                "title": "Overdue Task",

                "message": f"Task '{str(task.get('description', ''))[:50]}' was due on {task.get('due_date')}",

                "lead_id": task.get("lead_id", ""),

                "lead_name": str(task.get("description", ""))[:30],

                "task_id": task.get("id", ""),

                "severity": "high",

                "urgency": "urgent",

                "is_read": False,

                "is_auto": True,

                "created_at": now_iso,

                "created_at_dt": now_dt,

            }

        )



    hot_cutoff = (now_dt - timedelta(hours=48)).isoformat()

    hot_base = {

        "$and": [

            {

                "$or": [

                    {"updated_at": {"$gte": hot_cutoff}},

                    {"updated_at_dt": {"$gte": now_dt - timedelta(hours=48)}},

                ]

            },

            {

                "$or": [

                    {"temperature": {"$regex": r"^hot$", "$options": "i"}},

                ]

            },

        ]

    }

    hot_leads = await db.leads.find(

        _merge_scope(hot_base, scope),

        {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "full_name": 1, "temperature": 1},

    ).to_list(30)

    for lead in hot_leads:

        name = lead.get("full_name") or f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()

        auto.append(

            {

                "id": f"auto-hot-{lead['id']}",

                "type": "hot_lead",

                "title": "Hot Lead Alert",

                "message": f"{name} is a high-priority lead — follow up within 48 hours",

                "lead_id": lead["id"],

                "lead_name": name,

                "severity": "high",

                "urgency": "urgent",

                "is_read": False,

                "is_auto": True,

                "created_at": now_iso,

                "created_at_dt": now_dt,

            }

        )



    call_cutoff = now_dt - timedelta(hours=48)

    call_cutoff_iso = call_cutoff.isoformat()

    call_base = {

        "$and": [

            {

                "$or": [

                    {"created_at": {"$gte": call_cutoff_iso}},

                    {"created_at_dt": {"$gte": call_cutoff}},

                ]

            },

            {

                "$or": [

                    {"duration": {"$gt": 120}},

                    {"structured_extraction.disposition": {"$in": list(_HIGH_INTENT_DISPOSITIONS)}},

                    {"transcript": {"$regex": _INTENT_TRANSCRIPT_REGEX}},

                ]

            },

        ]

    }

    if scope:

        scoped_leads = await db.leads.find(scope, {"_id": 0, "id": 1}).to_list(5000)

        lead_ids = [l["id"] for l in scoped_leads if l.get("id")]

        if not lead_ids:

            recent_calls = []

        else:

            call_query = _merge_scope(call_base, {"lead_id": {"$in": lead_ids}})

            recent_calls = await db.call_history.find(

                call_query,

                {"_id": 0, "id": 1, "lead_id": 1, "duration": 1, "transcript": 1, "structured_extraction": 1},

            ).to_list(30)

    else:

        recent_calls = await db.call_history.find(

            call_base,

            {"_id": 0, "id": 1, "lead_id": 1, "duration": 1, "transcript": 1, "structured_extraction": 1},

        ).to_list(30)



    for call in recent_calls:

        lead_id = call.get("lead_id") or ""

        se = call.get("structured_extraction") or {}

        summary = (se.get("call_summary") or "")[:120]

        if not summary and call.get("transcript"):

            summary = str(call["transcript"])[:120] + "..."

        if not summary:

            summary = f"High-intent call ({call.get('duration', 0)}s)"

        auto.append(

            {

                "id": f"auto-call-{call.get('id', lead_id)}",

                "type": "ai_call_summary",

                "title": "AI Call Summary",

                "message": summary,

                "lead_id": lead_id,

                "lead_name": "",

                "severity": "medium",

                "urgency": "action_needed",

                "is_read": False,

                "is_auto": True,

                "created_at": now_iso,

                "created_at_dt": now_dt,

            }

        )



    stale_cutoff = (now_dt - timedelta(days=7)).isoformat()

    stale_base = {

        "$and": [

            {"updated_at": {"$lt": stale_cutoff}},

            {

                "$or": [

                    {"temperature": {"$regex": r"^cold$", "$options": "i"}},

                    {"status": {"$regex": RNR_STATUS_REGEX}},

                    {"lead_status": {"$regex": RNR_STATUS_REGEX}},

                    {"is_rnr": True},

                ]

            },

        ]

    }

    stale_leads = await db.leads.find(

        _merge_scope(stale_base, scope),

        {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "full_name": 1, "updated_at": 1},

    ).to_list(30)

    for lead in stale_leads:

        name = lead.get("full_name") or f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()

        updated_dt = _parse_ts(lead.get("updated_at"), now_dt)

        days_ago = int((now_dt - updated_dt).total_seconds() / 86400)

        auto.append(

            {

                "id": f"auto-stale-{lead['id']}",

                "type": "stale_followup",

                "title": "Stale Follow-up",

                "message": f"{name} (RNR/Cold) has had no activity for {days_ago} days",

                "lead_id": lead["id"],

                "lead_name": name,

                "severity": "medium",

                "urgency": "action_needed",

                "is_read": False,

                "is_auto": True,

                "created_at": now_iso,

                "created_at_dt": now_dt,

            }

        )



    rnr_cutoff = (now_dt - timedelta(hours=24)).isoformat()

    rnr_base = {

        "$and": [

            {"updated_at": {"$lt": rnr_cutoff}},

            {

                "$or": [

                    {"status": {"$regex": RNR_STATUS_REGEX}},

                    {"lead_status": {"$regex": RNR_STATUS_REGEX}},

                    {"is_rnr": True},

                ]

            },

        ]

    }

    rnr_leads = await db.leads.find(

        _merge_scope(rnr_base, scope),

        {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "full_name": 1, "updated_at": 1},

    ).to_list(30)

    for lead in rnr_leads:

        name = lead.get("full_name") or f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()

        updated_dt = _parse_ts(lead.get("updated_at"), now_dt)

        hours_ago = int((now_dt - updated_dt).total_seconds() / 3600)

        auto.append(

            {

                "id": f"auto-rnr-{lead['id']}",

                "type": "rnr_followup",

                "title": "RNR Follow-up Needed",

                "message": f"{name} hasn't been followed up — last attempt was {hours_ago}h ago",

                "lead_id": lead["id"],

                "lead_name": name,

                "severity": "high",

                "urgency": "urgent",

                "is_read": False,

                "is_auto": True,

                "created_at": now_iso,

                "created_at_dt": now_dt,

            }

        )

    for n in auto:
        n["title"] = sanitize_notification_text(n.get("title", ""))
        n["message"] = sanitize_notification_text(n.get("message", ""))

    return auto





@router.get("")

async def get_notifications(

    unread_only: bool = False,

    current_user: dict = Depends(get_current_user),

    db=Depends(get_db),

):

    query: Dict[str, Any] = _stored_notifications_query(current_user)

    if unread_only:
        unread = _unread_filter()
        query = {"$and": [query, unread]} if query else unread

    stored = await db.notifications.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)

    user_row = await db.users.find_one(
        {"id": current_user["id"]},
        {"_id": 0, "notification_dismissals": 1},
    ) or {}
    dismissed = set(user_row.get("notification_dismissals") or [])

    auto_notifications = [

        n

        for n in await _build_auto_notifications(db, current_user)

        if n.get("id") not in dismissed

    ]



    all_notifications = stored + auto_notifications

    all_notifications.sort(key=lambda n: n.get("created_at", ""), reverse=True)

    return all_notifications[:100]





@router.put("/read-all")
async def mark_all_notifications_read(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    uid = current_user["id"]
    auto_ids = [n["id"] for n in await _build_auto_notifications(db, current_user)]
    user = await db.users.find_one({"id": uid}, {"_id": 0, "notification_dismissals": 1}) or {}
    merged = list(dict.fromkeys((user.get("notification_dismissals") or []) + auto_ids))[-_MAX_DISMISSALS:]
    await db.users.update_one({"id": uid}, {"$set": {"notification_dismissals": merged}})

    unread = _unread_filter()
    role = (current_user.get("role") or "sales").lower()
    marked_stored = 0
    if role == "admin":
        result = await db.notifications.update_many(unread, {"$set": {"is_read": True}})
        marked_stored = result.modified_count
    else:
        result1 = await db.notifications.update_many(
            {"$and": [{"recipient_user_id": uid}, unread]},
            {"$set": {"is_read": True}},
        )
        result2 = await db.notifications.update_many(
            {
                "$and": [
                    unread,
                    {
                        "$or": [
                            {"recipient_user_id": {"$exists": False}},
                            {"recipient_user_id": None},
                            {"recipient_user_id": ""},
                        ]
                    },
                ]
            },
            {"$set": {"is_read": True}},
        )
        marked_stored = result1.modified_count + result2.modified_count

    return {
        "message": "All notifications marked as read",
        "dismissed_auto": len(auto_ids),
        "marked_stored": marked_stored,
    }


@router.put("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    if notification_id.startswith("auto-"):
        uid = current_user["id"]
        user = await db.users.find_one({"id": uid}, {"_id": 0, "notification_dismissals": 1}) or {}
        cur = list(user.get("notification_dismissals") or [])
        if notification_id not in cur:
            cur.append(notification_id)
            cur = cur[-_MAX_DISMISSALS:]
            await db.users.update_one({"id": uid}, {"$set": {"notification_dismissals": cur}})
        return {"message": "Notification marked as read"}

    role = (current_user.get("role") or "sales").lower()
    filt: Dict[str, Any] = {"$and": [{"id": notification_id}, _unread_filter()]}
    if role != "admin":
        filt["$and"].append({"$or": _recipient_scope_filter(current_user)})
    await db.notifications.update_one(filt, {"$set": {"is_read": True}})
    return {"message": "Notification marked as read"}


