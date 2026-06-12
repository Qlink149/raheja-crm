import re
import uuid
import httpx
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase
from ..models.lead import LeadDetail
from ..utils.csv_processor import (
    process_row_to_lead,
    process_lead_upload_row,
    process_call_report_row_to_call_history_and_lead_patches,
)
from ..core.config import settings
from .futwork_push import post_one_lead_to_futwork
from .qualification_buckets import (
    VALID_DASHBOARD_BUCKETS,
    build_base_query,
    bucket_query,
)

logger = logging.getLogger(__name__)


def _safe_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Stringify CSV row values so they round-trip cleanly through Mongo + JSON."""
    out: Dict[str, Any] = {}
    for k, v in (row or {}).items():
        if v is None:
            out[str(k)] = ""
        else:
            try:
                out[str(k)] = "" if (isinstance(v, float) and v != v) else str(v)
            except Exception:
                out[str(k)] = ""
    return out


def _dedupe_leads_for_futwork(leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One Futwork POST per client_lead_id; last row in upload order wins."""
    by_client: Dict[str, Dict[str, Any]] = {}
    tail: List[Dict[str, Any]] = []
    for lead in leads:
        cid = str(lead.get("client_lead_id") or "").strip()
        if cid:
            by_client[cid] = lead
        else:
            tail.append(lead)
    return list(by_client.values()) + tail


class LeadService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    def _build_leads_query(
        self,
        search: Optional[str],
        filters: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Mongo match for list/count."""
        import re

        parts: List[Dict[str, Any]] = []

        if filters:
            filters = dict(filters)

        if search:
            esc = re.escape(search)
            digits = re.sub(r"\D+", "", search)
            ors = [
                {"full_name": {"$regex": esc, "$options": "i"}},
                {"first_name": {"$regex": esc, "$options": "i"}},
                {"last_name": {"$regex": esc, "$options": "i"}},
                {"project": {"$regex": esc, "$options": "i"}},
                {"mobile": {"$regex": esc, "$options": "i"}},
                {"client_lead_id": {"$regex": esc, "$options": "i"}},
            ]
            if digits:
                ors.append({"mobile_digits": {"$regex": digits}})
                if len(digits) > 10:
                    ors.append({"mobile_digits": {"$regex": digits[-10:]}})
            parts.append({"$or": ors})

        other: Dict[str, Any] = {}
        vip_expand = False
        dashboard_bucket = None
        days = None
        start_date = None
        end_date = None
        date_project = None

        if filters:
            dashboard_bucket = filters.pop("dashboard_bucket", None)
            raw_days = filters.pop("days", None)
            if raw_days is not None and raw_days != "":
                try:
                    days = int(raw_days)
                except (TypeError, ValueError):
                    days = None
            start_date = filters.pop("start_date", None)
            end_date = filters.pop("end_date", None)
            if dashboard_bucket and "project" in filters:
                date_project = filters.pop("project")

        skip_qual_filters = bool(
            dashboard_bucket
            and str(dashboard_bucket).strip().lower() in VALID_DASHBOARD_BUCKETS
        )

        if filters:
            for key, value in filters.items():
                if value is None or value == "all" or value == "":
                    continue
                if skip_qual_filters and key in (
                    "qualification_category",
                    "intent_category",
                    "project",
                    "status",
                    "sales_qualification",
                ):
                    continue
                if key == "qualification_category":
                    other["qualification_category"] = value
                    continue
                if key == "upload_batch_id":
                    other["upload_batch_id"] = value
                    continue
                if key == "disposition":
                    esc = re.escape(str(value))
                    parts.append(
                        {
                            "$or": [
                                {
                                    "disposition": {
                                        "$regex": f"^{esc}$",
                                        "$options": "i",
                                    }
                                },
                                {
                                    "ai_disposition": {
                                        "$regex": f"^{esc}$",
                                        "$options": "i",
                                    }
                                },
                            ]
                        }
                    )
                    continue
                if key == "project":
                    if str(value) == "__none__":
                        other["$or"] = [
                            {"project": {"$exists": False}},
                            {"project": None},
                            {"project": ""},
                        ]
                    else:
                        other["project"] = {
                            "$regex": f"^{re.escape(str(value))}$",
                            "$options": "i",
                        }
                    continue
                if key == "assigned_rep":
                    esc = re.escape(str(value))
                    other["$or"] = [
                        {"assigned_to_name": {"$regex": f"^{esc}$", "$options": "i"}},
                        {"assigned_to": {"$regex": f"^{esc}$", "$options": "i"}},
                    ]
                    continue
                if key == "assigned_user_id":
                    other["assigned_user_id"] = value
                    continue
                if key == "sales_qualification":
                    other["sales_qualification"] = value
                    continue
                if key == "status":
                    other["status"] = value
                    continue
                else:
                    other[key] = value

        has_date_filter = days is not None or start_date or end_date

        if skip_qual_filters:
            base = build_base_query(date_project, days, start_date, end_date)
            parts.append(bucket_query(base, str(dashboard_bucket).strip().lower()))
        elif has_date_filter:
            base = build_base_query(date_project, days, start_date, end_date)
            if base:
                parts.append(base)

        if other:
            parts.append(other)

        if not parts:
            return {}
        if len(parts) == 1:
            return parts[0]
        return {"$and": parts}

    async def count_leads(
        self,
        search: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        query = self._build_leads_query(search, filters)
        return await self.count_by_query(query)

    async def count_by_query(self, query: Dict[str, Any]) -> int:
        if not query:
            return await self.db.leads.count_documents({})
        return await self.db.leads.count_documents(query)

    async def get_leads(
        self,
        skip: int = 0,
        limit: int = 50,
        search: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        query = self._build_leads_query(search, filters)
        return await self.find_leads_by_query(query, skip, limit)

    async def find_leads_by_query(
        self,
        query: Dict[str, Any],
        skip: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        match = query if query else {}
        cursor = (
            self.db.leads.find(match, {"_id": 0})
            .sort("updated_at", -1)
            .skip(skip)
            .limit(limit)
        )
        return await cursor.to_list(length=limit)

    async def get_lead_by_id(self, lead_id: str) -> Optional[Dict[str, Any]]:
        doc = await self.db.leads.find_one({"id": lead_id}, {"_id": 0})
        return doc

    async def upsert_from_csv(
        self,
        rows: List[Dict[str, Any]],
        *,
        upload_batch_id: Optional[str] = None,
        upload_batch_name: Optional[str] = None,
        auto_assign_new: bool = True,
    ) -> Dict[str, Any]:
        """Upsert leads from CSV rows.

        Returns:
            {
              "processed": int,    # rows successfully upserted
              "new": int,
              "updated": int,
              "failed_rows": [
                  {"row_index": int, "reason": str, "raw": dict},
                  ...
              ],
            }

        Each row is wrapped in try/except so a single bad row never aborts the
        whole upload. The original row is preserved (shallow-stringified) so we
        can stream it back out as a downloadable CSV.
        """
        processed_count = 0
        new_count = 0
        updated_count = 0
        failed_rows: List[Dict[str, Any]] = []

        for idx, row in enumerate(rows):
            try:
                lead_data = process_lead_upload_row(row)
            except Exception as e:
                logger.warning("CSV row %s failed mapping: %s", idx, e)
                failed_rows.append({
                    "row_index": idx,
                    "reason": f"row mapping failed: {e}",
                    "raw": _safe_row(row),
                })
                continue

            client_lead_id = str(lead_data.get("client_lead_id") or "").strip()
            if not client_lead_id:
                failed_rows.append({
                    "row_index": idx,
                    "reason": "missing Lead ID (client_lead_id)",
                    "raw": _safe_row(row),
                })
                continue

            try:
                lead_data["external_id"] = client_lead_id
                if upload_batch_id:
                    lead_data["upload_batch_id"] = upload_batch_id
                if upload_batch_name:
                    lead_data["upload_batch_name"] = upload_batch_name

                existing = await self.db.leads.find_one(
                    {"client_lead_id": client_lead_id},
                    {"_id": 1, "id": 1, "futwork_lead_id": 1},
                )

                if existing:
                    patch = dict(lead_data)
                    patch.pop("futwork_sync_status", None)
                    if str(existing.get("futwork_lead_id") or "").strip():
                        patch.pop("futwork_lead_id", None)
                    patch["updated_at"] = datetime.utcnow()
                    await self.db.leads.update_one(
                        {"client_lead_id": client_lead_id},
                        {"$set": patch},
                    )
                    updated_count += 1
                else:
                    doc = {
                        **lead_data,
                        "id": str(uuid.uuid4()),
                        "futwork_sync_status": "pending",
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow(),
                    }
                    await self.db.leads.insert_one(doc)
                    new_count += 1
                    if auto_assign_new:
                        from .assignment_service import AssignmentService

                        await AssignmentService(self.db).auto_assign_lead(doc["id"])
                processed_count += 1
            except Exception as e:
                logger.exception("CSV row %s failed upsert", idx)
                failed_rows.append({
                    "row_index": idx,
                    "reason": f"db upsert failed: {e}",
                    "raw": _safe_row(row),
                })

        return {
            "processed": processed_count,
            "new": new_count,
            "updated": updated_count,
            "failed_rows": failed_rows,
        }

    async def upsert_call_report_from_csv(
        self,
        rows: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Ingest Futwork "unmasked call report" CSV rows.

        - Upsert into `call_history` using callSid as id (call-level truth).
        - Update `leads` with last_call_* snapshot fields (non-destructive).
        """
        processed = 0
        call_history_upserted = 0
        leads_updated = 0
        failed_rows: List[Dict[str, Any]] = []

        for idx, row in enumerate(rows or []):
            try:
                call_history_set, lead_set, call_sid = (
                    process_call_report_row_to_call_history_and_lead_patches(row)
                )
            except Exception as e:
                failed_rows.append(
                    {
                        "row_index": idx,
                        "reason": f"call report mapping failed: {e}",
                        "raw": _safe_row(row),
                    }
                )
                continue

            if not call_sid:
                failed_rows.append(
                    {
                        "row_index": idx,
                        "reason": "missing callSid",
                        "raw": _safe_row(row),
                    }
                )
                continue

            mobile_digits = str(lead_set.get("mobile_digits") or "").strip()
            if not mobile_digits:
                failed_rows.append(
                    {
                        "row_index": idx,
                        "reason": "missing phone/mobile_digits",
                        "raw": _safe_row(row),
                    }
                )
                continue

            # Only set value-bearing fields (avoid wiping with blanks)
            call_history_set = {
                k: v
                for k, v in (call_history_set or {}).items()
                if v is not None and v != "" and k != "_id"
            }
            lead_set = {
                k: v
                for k, v in (lead_set or {}).items()
                if v is not None and v != "" and k != "_id"
            }

            try:
                # Upsert call_history (call-level truth)
                await self.db.call_history.update_one(
                    {"id": call_sid},
                    {
                        "$set": call_history_set,
                        "$setOnInsert": {"created_at": call_history_set.get("created_at") or datetime.utcnow()},
                        "$push": {"status_history": {"status": call_history_set.get("status", ""), "at": datetime.utcnow()}},
                    },
                    upsert=True,
                )
                call_history_upserted += 1

                # Update lead snapshot (best-effort; don't create leads from call report)
                lead_update = dict(lead_set)
                lead_update.pop("mobile_digits", None)
                lead_update.pop("mobile", None)
                if lead_update:
                    cid = str(
                        lead_update.get("client_lead_id")
                        or lead_update.get("external_id")
                        or ""
                    ).strip()
                    flt: Optional[Dict[str, Any]] = None
                    if cid:
                        flt = {"client_lead_id": cid}
                    elif mobile_digits:
                        flt = {"mobile_digits": mobile_digits}
                    if flt:
                        lead_update.pop("futwork_lead_id", None)
                        res = await self.db.leads.update_one(
                            flt,
                            {"$set": lead_update},
                        )
                        if res.matched_count:
                            leads_updated += 1

                processed += 1
            except Exception as e:
                logger.exception("Call report row %s failed upsert", idx)
                failed_rows.append(
                    {
                        "row_index": idx,
                        "reason": f"db upsert failed: {e}",
                        "raw": _safe_row(row),
                    }
                )

        return {
            "processed": processed,
            "call_history_upserted": call_history_upserted,
            "leads_updated": leads_updated,
            "failed_rows": failed_rows,
        }

    async def update_disposition(self, lead_id: str, disposition: str) -> bool:
        """Update disposition on a lead. Returns True if a document was found and updated."""
        result = await self.db.leads.update_one(
            {"id": lead_id},
            {"$set": {"disposition": disposition, "updated_at": datetime.utcnow()}}
        )
        return result.matched_count > 0

    async def ensure_residential_alias(self, lead_id: str) -> None:
        """Ensure current_residential_location mirrors current_residence_location for a lead."""
        lead = await self.db.leads.find_one(
            {"id": lead_id},
            {"current_residence_location": 1, "current_residential_location": 1},
        )
        if not lead:
            return
        src = (lead.get("current_residence_location") or "").strip()
        alias = (lead.get("current_residential_location") or "").strip()
        if src and not alias:
            await self.db.leads.update_one(
                {"id": lead_id},
                {"$set": {"current_residential_location": src, "updated_at": datetime.utcnow()}},
            )

    async def apply_lead_futwork_sync(
        self,
        *,
        client_lead_id: str,
        status: str,
        futwork_lead_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
    ) -> None:
        """Update futwork_sync_status for a lead matched by client_lead_id only."""
        cid = str(client_lead_id or "").strip()
        if not cid:
            return
        doc: Dict[str, Any] = {
            "futwork_sync_status": status,
            "updated_at": datetime.utcnow(),
        }
        if futwork_lead_id:
            doc["futwork_lead_id"] = futwork_lead_id
        if campaign_id:
            doc["campaign_id"] = campaign_id
        await self.db.leads.update_one({"client_lead_id": cid}, {"$set": doc})

    @staticmethod
    def _bulk_futwork_push_eligible_query() -> Dict[str, Any]:
        """Leads eligible for DB bulk Futwork push (pending/failed, valid phone + client_lead_id)."""
        return {
            "client_lead_id": {"$exists": True, "$nin": ["", None]},
            "mobile_digits": {"$regex": r"^\d{10}$"},
            "$or": [
                {"futwork_sync_status": {"$in": ["pending", "failed"]}},
                {"futwork_sync_status": {"$exists": False}},
                {"futwork_sync_status": None},
            ],
        }

    async def count_leads_eligible_for_bulk_futwork_push(self) -> int:
        return await self.db.leads.count_documents(self._bulk_futwork_push_eligible_query())

    async def fetch_leads_eligible_for_bulk_futwork_push(
        self,
        limit: int,
    ) -> List[Dict[str, Any]]:
        lim = max(1, int(limit))
        cursor = (
            self.db.leads.find(self._bulk_futwork_push_eligible_query(), {"_id": 0})
            .sort("created_at", 1)
            .limit(lim)
        )
        return await cursor.to_list(length=lim)

    async def tag_leads_with_upload_batch(
        self,
        lead_ids: List[str],
        *,
        upload_batch_id: str,
        upload_batch_name: str,
    ) -> int:
        """Set upload_batch_id/name on leads before Futwork push."""
        ids = [str(i).strip() for i in lead_ids if str(i).strip()]
        if not ids:
            return 0
        batch_id = (upload_batch_id or "").strip()
        batch_name = (upload_batch_name or "").strip()
        if not batch_id:
            return 0
        result = await self.db.leads.update_many(
            {"id": {"$in": ids}},
            {
                "$set": {
                    "upload_batch_id": batch_id,
                    "upload_batch_name": batch_name,
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        return int(result.modified_count)

    async def leads_for_futwork_push_by_batch(
        self,
        upload_batch_id: str,
        *,
        include_repushed: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Load leads from DB for Futwork push after CSV upload.

        By default only pending/failed sync rows are pushed (avoids duplicate
        pushes on re-upload of already-pushed leads).
        """
        batch_id = (upload_batch_id or "").strip()
        if not batch_id:
            return []
        query: Dict[str, Any] = {
            "upload_batch_id": batch_id,
            "client_lead_id": {"$exists": True, "$nin": ["", None]},
        }
        if not include_repushed:
            query["$or"] = [
                {"futwork_sync_status": {"$in": ["pending", "failed"]}},
                {"futwork_sync_status": {"$exists": False}},
                {"futwork_sync_status": None},
            ]
        cursor = self.db.leads.find(query, {"_id": 0})
        return await cursor.to_list(length=50000)

    async def push_to_futwork(
        self,
        leads: List[Dict[str, Any]],
        campaign_id: Optional[str] = None,
    ) -> Tuple[int, int]:
        """
        Push leads to Futwork Platform API.

        Correct endpoint: POST https://platform.futwork.ai/api/campaigns/{campaignId}/leads
        Correct payload per lead:
            {
              "recipientPhoneNumber": "9999789877",
              "recipientData": {
                "customer_name": "abcd xyz"
              }
            }
        One HTTP request is made per lead (Futwork does not accept batch arrays).

        When Futwork's response carries a lead id, we persist it on the
        matching lead document as `futwork_lead_id` so post-call webhooks can
        correlate by id instead of falling back to phone digits.
        """
        if not settings.FUTWORK_API_KEY or not settings.FUTWORK_CAMPAIGN_ID:
            logger.warning("Futwork credentials missing. Skipping direct push.")
            return (0, 0)

        n_in = len(leads)
        leads = _dedupe_leads_for_futwork(leads)
        if len(leads) != n_in:
            logger.info("Futwork push: deduped %s -> %s leads by client_lead_id", n_in, len(leads))

        pushed = 0
        failed = 0
        try:
            async with httpx.AsyncClient(timeout=30.0) as http_client:
                for lead in leads:
                    ok, _ = await post_one_lead_to_futwork(
                        http_client,
                        self.db,
                        lead,
                        campaign_id=campaign_id,
                    )
                    if ok:
                        pushed += 1
                    else:
                        failed += 1

            logger.info(
                "Futwork push complete: pushed=%s, failed=%s, total=%s",
                pushed,
                failed,
                len(leads),
            )
            return (pushed, failed)
        except Exception as e:
            logger.error("Futwork push_to_futwork error: %s", e, exc_info=True)
            return (pushed, failed)
