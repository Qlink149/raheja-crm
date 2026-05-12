import uuid
import httpx
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase
from ..models.lead import LeadDetail
from ..utils.csv_processor import (
    process_row_to_lead,
    generate_seed_key,
    process_call_report_row_to_call_history_and_lead_patches,
)
from ..core.config import settings

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


def _ten_digit_key_for_futwork(lead: Dict[str, Any]) -> str:
    """Same normalization as push_to_futwork loop: last 10 digits for dedupe / push."""
    raw_phone = (
        lead.get("recipientPhoneNumber")
        or lead.get("mobile_digits")
        or lead.get("mobile", "")
    )
    db_digits = (lead.get("mobile_digits") or "").strip()
    db_digits = "".join(c for c in db_digits if c.isdigit())[-10:]
    if not raw_phone:
        return db_digits if len(db_digits) == 10 else ""
    phone = "".join(c for c in str(raw_phone) if c.isdigit())[-10:]
    match_digits = phone if len(phone) == 10 else db_digits
    if len(phone) == 10:
        return phone
    return match_digits if len(match_digits) == 10 else ""


def _dedupe_leads_for_futwork(leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One Futwork POST per 10-digit mobile; last row in upload order wins."""
    by_digits: Dict[str, Dict[str, Any]] = {}
    tail: List[Dict[str, Any]] = []
    for lead in leads:
        key = _ten_digit_key_for_futwork(lead)
        if len(key) == 10:
            by_digits[key] = lead
        else:
            tail.append(lead)
    return list(by_digits.values()) + tail


class LeadService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    def _build_leads_query(
        self,
        search: Optional[str],
        filters: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Mongo match for list/count. VIP expands legacy rows missing `is_vip`."""
        import re

        parts: List[Dict[str, Any]] = []

        if search:
            esc = re.escape(search)
            digits = re.sub(r"\D+", "", search)
            ors = [
                {"full_name": {"$regex": esc, "$options": "i"}},
                {"first_name": {"$regex": esc, "$options": "i"}},
                {"last_name": {"$regex": esc, "$options": "i"}},
                {"project": {"$regex": esc, "$options": "i"}},
                {"mobile": {"$regex": esc, "$options": "i"}},
            ]
            if digits:
                ors.append({"mobile_digits": {"$regex": digits}})
                if len(digits) > 10:
                    ors.append({"mobile_digits": {"$regex": digits[-10:]}})
            parts.append({"$or": ors})

        other: Dict[str, Any] = {}
        vip_expand = False
        if filters:
            for key, value in filters.items():
                if value is None or value == "all" or value == "":
                    continue
                if key == "qualification_category":
                    other["qualification_category"] = value
                    continue
                if key == "is_vip" and value is True:
                    vip_expand = True
                elif key == "is_vip":
                    other[key] = value
                else:
                    other[key] = value

        if vip_expand:
            parts.append(
                {
                    "$or": [
                        {"is_vip": True},
                        {"temperature": "Hot"},
                        {"budget_category": {"$in": ["5 Cr+", "2-5 Cr"]}},
                    ]
                }
            )

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
        return await self.db.leads.count_documents(query)

    async def get_leads(self,
                        skip: int = 0,
                        limit: int = 50,
                        search: Optional[str] = None,
                        filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        query = self._build_leads_query(search, filters)
        cursor = self.db.leads.find(query, {"_id": 0}).sort("updated_at", -1).skip(skip).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_lead_by_id(self, lead_id: str) -> Optional[Dict[str, Any]]:
        doc = await self.db.leads.find_one({"id": lead_id}, {"_id": 0})
        return doc

    async def upsert_from_csv(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
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
                lead_data = process_row_to_lead(row)
            except Exception as e:
                logger.warning("CSV row %s failed mapping: %s", idx, e)
                failed_rows.append({
                    "row_index": idx,
                    "reason": f"row mapping failed: {e}",
                    "raw": _safe_row(row),
                })
                continue

            mobile_digits = lead_data.get("mobile_digits") or ""
            if not mobile_digits:
                failed_rows.append({
                    "row_index": idx,
                    "reason": "missing or invalid phone number",
                    "raw": _safe_row(row),
                })
                continue

            try:
                seed_key = generate_seed_key(row)
                lead_data["_seed_key"] = seed_key
                lead_data["futwork_sync_status"] = "pending"

                existing = await self.db.leads.find_one(
                    {"_seed_key": seed_key}, {"_id": 1}
                )

                if existing:
                    await self.db.leads.update_one(
                        {"_seed_key": seed_key},
                        {"$set": lead_data},
                    )
                    updated_count += 1
                else:
                    lead_data["id"] = str(uuid.uuid4())
                    lead_data["created_at"] = datetime.utcnow()
                    await self.db.leads.insert_one(lead_data)
                    new_count += 1
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
                    res = await self.db.leads.update_one(
                        {"mobile_digits": mobile_digits},
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

    @staticmethod
    def _extract_futwork_lead_id(body: Any) -> str:
        """Best-effort scrape of the lead id Futwork returns after a successful push.

        Their docs only specify the request body, so we accept several common
        shapes: a flat object with `leadId` / `id` / `_id`, or a wrapper such
        as `{ "data": { ... } }` / `{ "lead": { ... } }`.
        """
        if not isinstance(body, dict):
            return ""
        for key in ("leadId", "lead_id", "id", "_id"):
            val = body.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        for wrapper in ("data", "lead", "result"):
            inner = body.get(wrapper)
            if isinstance(inner, dict):
                fid = LeadService._extract_futwork_lead_id(inner)
                if fid:
                    return fid
        return ""

    async def apply_lead_futwork_sync(
        self,
        *,
        mobile_digits_10: str,
        status: str,
        futwork_lead_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
    ) -> None:
        """Update futwork_sync_status (and optional ids) for a lead matched by 10-digit mobile."""
        if len(mobile_digits_10) != 10:
            return
        flt: Dict[str, Any] = {"mobile_digits": mobile_digits_10}
        doc: Dict[str, Any] = {
            "futwork_sync_status": status,
            "updated_at": datetime.utcnow(),
        }
        if futwork_lead_id:
            doc["futwork_lead_id"] = futwork_lead_id
        if campaign_id:
            doc["campaign_id"] = campaign_id
        await self.db.leads.update_one(flt, {"$set": doc})

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
            logger.info("Futwork push: deduped %s -> %s leads by mobile", n_in, len(leads))

        endpoint = (
            f"https://platform.futwork.ai/api/campaigns/"
            f"{settings.FUTWORK_CAMPAIGN_ID}/leads"
        )
        headers = {
            "x-api-key": settings.FUTWORK_API_KEY,
            "Content-Type": "application/json",
        }

        pushed = 0
        failed = 0
        try:
            async with httpx.AsyncClient(timeout=30.0) as http_client:
                for lead in leads:
                    raw_phone = (
                        lead.get("recipientPhoneNumber")
                        or lead.get("mobile_digits")
                        or lead.get("mobile", "")
                    )
                    db_digits = (lead.get("mobile_digits") or "").strip()
                    db_digits = "".join(c for c in db_digits if c.isdigit())[-10:]

                    if not raw_phone:
                        if len(db_digits) == 10:
                            await self.apply_lead_futwork_sync(
                                mobile_digits_10=db_digits,
                                status="failed",
                                campaign_id=campaign_id,
                            )
                        failed += 1
                        continue

                    phone = "".join(c for c in str(raw_phone) if c.isdigit())[-10:]
                    match_digits = phone if len(phone) == 10 else db_digits

                    if len(phone) != 10:
                        logger.warning(
                            "Skipping lead due to invalid phone length: %s", phone
                        )
                        if len(match_digits) == 10:
                            await self.apply_lead_futwork_sync(
                                mobile_digits_10=match_digits,
                                status="failed",
                                campaign_id=campaign_id,
                            )
                        failed += 1
                        continue

                    name = (
                        lead.get("customer_name")
                        or lead.get("full_name")
                        or "Unknown"
                    )

                    payload = {
                        "recipientPhoneNumber": phone,
                        "recipientData": {
                            "customer_name": name,
                        },
                    }

                    try:
                        logger.info(
                            "FUTWORK PUSH REQUEST | URL: %s | Payload: %s",
                            endpoint,
                            payload,
                        )
                        response = await http_client.post(
                            endpoint, json=payload, headers=headers
                        )
                        logger.info(
                            "FUTWORK PUSH RESPONSE | Status: %s | Body: %s",
                            response.status_code,
                            response.text,
                        )
                        response.raise_for_status()
                        pushed += 1

                        try:
                            body = response.json()
                        except Exception:
                            body = None
                        futwork_lead_id = self._extract_futwork_lead_id(body)
                        await self.apply_lead_futwork_sync(
                            mobile_digits_10=phone,
                            status="pushed",
                            futwork_lead_id=futwork_lead_id or None,
                            campaign_id=campaign_id,
                        )
                    except httpx.HTTPStatusError as e:
                        logger.error(
                            "Failed to push lead %s to Futwork | HTTPStatusError: %s | Response Body: %s",
                            phone,
                            e,
                            e.response.text if e.response else "",
                            exc_info=True,
                        )
                        await self.apply_lead_futwork_sync(
                            mobile_digits_10=phone,
                            status="failed",
                            campaign_id=campaign_id,
                        )
                        failed += 1
                    except Exception as e:
                        logger.error(
                            "Failed to push lead %s to Futwork: %s",
                            phone,
                            e,
                            exc_info=True,
                        )
                        await self.apply_lead_futwork_sync(
                            mobile_digits_10=phone,
                            status="failed",
                            campaign_id=campaign_id,
                        )
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
