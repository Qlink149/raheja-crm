import uuid
import httpx
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from ..models.lead import LeadDetail
from ..utils.csv_processor import process_row_to_lead, generate_seed_key
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


class LeadService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    async def get_leads(self,
                        skip: int = 0,
                        limit: int = 50,
                        search: Optional[str] = None,
                        filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        import re
        query = {}
        if search:
            esc = re.escape(search)
            digits = re.sub(r"\D+", "", search)
            ors = [
                {'full_name': {'$regex': esc, '$options': 'i'}},
                {'first_name': {'$regex': esc, '$options': 'i'}},
                {'last_name': {'$regex': esc, '$options': 'i'}},
                {'project': {'$regex': esc, '$options': 'i'}},
                {'mobile': {'$regex': esc, '$options': 'i'}},
            ]
            if digits:
                ors.append({'mobile_digits': {'$regex': digits}})
                if len(digits) > 10:
                    ors.append({'mobile_digits': {'$regex': digits[-10:]}})
            query['$or'] = ors

        if filters:
            for key, value in filters.items():
                if value is not None and value != "all" and value != "":
                    query[key] = value

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

    async def update_disposition(self, lead_id: str, disposition: str) -> bool:
        """Update disposition on a lead. Returns True if a document was found and updated."""
        result = await self.db.leads.update_one(
            {"id": lead_id},
            {"$set": {"disposition": disposition, "updated_at": datetime.utcnow()}}
        )
        return result.matched_count > 0

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

    async def push_to_futwork(self, leads: List[Dict[str, Any]]) -> bool:
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
            return False

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
                    # Phone — prefer recipientPhoneNumber col, then normalized digits
                    phone = (
                        lead.get("recipientPhoneNumber")
                        or lead.get("mobile_digits")
                        or lead.get("mobile", "")
                    )
                    if not phone:
                        continue

                    # Name — prefer customer_name col (Futwork CSV header), then full_name
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
                        logger.info(f"FUTWORK PUSH REQUEST | URL: {endpoint} | Headers: {headers} | Payload: {payload}")
                        response = await http_client.post(
                            endpoint, json=payload, headers=headers
                        )
                        logger.info(f"FUTWORK PUSH RESPONSE | Status: {response.status_code} | Body: {response.text}")
                        response.raise_for_status()
                        pushed += 1

                        try:
                            body = response.json()
                        except Exception:
                            body = None
                        futwork_lead_id = self._extract_futwork_lead_id(body)
                        if futwork_lead_id:
                            digits_only = "".join(c for c in str(phone) if c.isdigit())[-10:]
                            if digits_only:
                                await self.db.leads.update_one(
                                    {"mobile_digits": digits_only},
                                    {"$set": {
                                        "futwork_lead_id": futwork_lead_id,
                                        "updated_at": datetime.utcnow(),
                                    }},
                                )
                    except httpx.HTTPStatusError as e:
                        logger.error(f"Failed to push lead {phone} to Futwork | HTTPStatusError: {e} | Response Body: {e.response.text}")
                        failed += 1
                    except Exception as e:
                        logger.error(f"Failed to push lead {phone} to Futwork: {e}")
                        failed += 1

            logger.info(
                f"Futwork push complete: pushed={pushed}, failed={failed}, "
                f"total={len(leads)}"
            )
            return failed == 0
        except Exception as e:
            logger.error(f"Futwork push_to_futwork error: {e}")
            return False
