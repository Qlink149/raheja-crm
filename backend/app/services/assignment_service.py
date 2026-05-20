"""Lead assignment: load-balanced auto-assign and manual assign."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from motor.motor_asyncio import AsyncIOMotorDatabase

from .notification_service import notify_lead_transferred, notify_new_lead_assigned

INACTIVE_STATUS_PATTERN = "lost|booked|closed|dropped|unqualified|not interested"


def rep_lead_filter(user_id: str, full_name: str) -> Dict[str, Any]:
    return {
        "$or": [
            {"assigned_user_id": user_id},
            {"assigned_to": full_name},
            {"assigned_to_name": full_name},
        ]
    }


class AssignmentService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    async def list_sales_reps(self) -> List[Dict[str, Any]]:
        cursor = self.db.users.find(
            {"role": "sales", "is_active": True},
            {"_id": 0, "id": 1, "email": 1, "full_name": 1},
        ).sort("full_name", 1)
        return await cursor.to_list(100)

    async def _active_lead_counts(self, user_ids: List[str]) -> Dict[str, int]:
        if not user_ids:
            return {}
        pipeline = [
            {
                "$match": {
                    "assigned_user_id": {"$in": user_ids},
                    "status": {
                        "$not": {
                            "$regex": INACTIVE_STATUS_PATTERN,
                            "$options": "i",
                        }
                    },
                }
            },
            {"$group": {"_id": "$assigned_user_id", "count": {"$sum": 1}}},
        ]
        rows = await self.db.leads.aggregate(pipeline).to_list(len(user_ids) + 1)
        return {str(r["_id"]): int(r["count"]) for r in rows if r.get("_id")}

    async def pick_assignee(self) -> Optional[Dict[str, Any]]:
        reps = await self.list_sales_reps()
        if not reps:
            return None
        ids = [r["id"] for r in reps]
        counts = await self._active_lead_counts(ids)
        return min(
            reps,
            key=lambda r: (counts.get(r["id"], 0), r.get("full_name") or ""),
        )

    async def auto_assign_lead(self, lead_id: str) -> Tuple[Optional[Dict[str, Any]], str]:
        lead = await self.db.leads.find_one({"id": lead_id}, {"_id": 0, "id": 1})
        if not lead:
            return None, "Lead not found"

        rep = await self.pick_assignee()
        if not rep:
            return None, "No active sales users found"

        ok = await self.assign_lead(lead_id, rep["id"], rep["full_name"])
        if not ok:
            return None, "Assignment failed"
        counts = await self._active_lead_counts([rep["id"]])
        rep = {**rep, "active_leads": counts.get(rep["id"], 0)}
        return rep, f"Auto-assigned to {rep['full_name']}"

    async def assign_lead(
        self,
        lead_id: str,
        assigned_user_id: str,
        assigned_name: Optional[str] = None,
        *,
        transfer_notes: str = "",
    ) -> bool:
        user = await self.db.users.find_one({"id": assigned_user_id}, {"_id": 0})
        if not user:
            return False

        lead = await self.db.leads.find_one({"id": lead_id}, {"_id": 0})
        if not lead:
            return False

        prev_user_id = lead.get("assigned_user_id") or ""
        prev_name = (
            lead.get("assigned_to_name")
            or lead.get("assigned_to")
            or ""
        )

        name = assigned_name or user.get("full_name") or ""
        now = datetime.utcnow()
        result = await self.db.leads.update_one(
            {"id": lead_id},
            {
                "$set": {
                    "assigned_user_id": assigned_user_id,
                    "assigned_to": name,
                    "assigned_to_name": name,
                    "assigned_at": now,
                    "updated_at": now,
                }
            },
        )
        if result.matched_count == 0:
            return False

        updated_lead = {**lead, "assigned_user_id": assigned_user_id, "assigned_to": name, "assigned_to_name": name}

        if prev_user_id and prev_user_id != assigned_user_id:
            await notify_lead_transferred(
                self.db,
                updated_lead,
                assigned_user_id,
                name,
                from_name=prev_name,
                notes=transfer_notes,
            )
        else:
            await notify_new_lead_assigned(
                self.db,
                updated_lead,
                assigned_user_id,
                name,
            )

        return True
