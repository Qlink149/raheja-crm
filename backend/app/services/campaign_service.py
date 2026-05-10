import uuid
import logging
import httpx
from datetime import datetime
from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from ..core.config import settings
from ..utils.campaign_stats import (
    default_live_status,
    map_stored_call_to_live_key,
)
from ..models.campaign import CampaignCurrentResponse, LiveLeadStatus
from .lead_service import LeadService

logger = logging.getLogger(__name__)

# Map internal agent IDs to human-readable names
AGENT_NAME_MAP = {
    "sales-closer": "Sales Closer Pro",
    "nurture-agent": "Lead Nurturer",
    "reactivation-agent": "Re-engagement Specialist",
}


def resolve_agent_name(agent_id: str) -> str:
    """Best-effort friendly name for an agent id.

    Internal slugs (e.g. ``sales-closer``) come from ``AGENT_NAME_MAP``.
    Futwork-issued ObjectIds (24 hex chars) get a short, deterministic label
    so the campaign info card never shows a raw 24-char hash.
    """
    if not agent_id:
        return ""
    mapped = AGENT_NAME_MAP.get(agent_id)
    if mapped:
        return mapped
    if len(agent_id) >= 8 and all(c in "0123456789abcdefABCDEF" for c in agent_id):
        return f"Futwork Agent ({agent_id[:6]}…{agent_id[-4:]})"
    return agent_id

class CampaignService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    async def get_campaigns(self) -> List[Dict[str, Any]]:
        docs = await self.db.campaigns.find().sort("created_at", -1).to_list(length=100)
        # Remove MongoDB _id so serialization doesn't fail
        for doc in docs:
            doc.pop("_id", None)
        return docs

    async def find_campaign_by_futwork_settings(self) -> Optional[Dict[str, Any]]:
        """Resolve the single campaign using FUTWORK_CAMPAIGN_ID from env."""
        fid = (settings.FUTWORK_CAMPAIGN_ID or "").strip()
        if not fid:
            return None
        doc = await self.db.campaigns.find_one(
            {"$or": [{"futwork_campaign_id": fid}, {"id": fid}]},
            {"_id": 0},
        )
        env_agent_id = (settings.FUTWORK_AGENT_ID or "").strip()
        env_agent_name = resolve_agent_name(env_agent_id)

        if not doc:
            # Auto-create a placeholder campaign so the UI always has a campaign to render
            new_campaign = {
                "id": str(uuid.uuid4()),
                "name": f"Default Campaign",
                "futwork_campaign_id": fid,
                "status": "running",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "live_status": default_live_status(),
                "dispositions": {
                    "interested": 0,
                    "semiInterested": 0,
                    "callback": 0,
                    "notInterested": 0,
                    "noAnswer": 0
                },
                "total_leads": 0,
            }
            if env_agent_id:
                new_campaign["agent_id"] = env_agent_id
                new_campaign["agent_name"] = env_agent_name
                new_campaign["agent"] = env_agent_name
            await self.db.campaigns.insert_one(new_campaign.copy())
            new_campaign.pop("_id", None)
            doc = new_campaign
        else:
            # Backfill agent metadata on legacy docs that pre-date FUTWORK_AGENT_ID wiring.
            if env_agent_id and not (doc.get("agent_id") or "").strip():
                await self.db.campaigns.update_one(
                    {"id": doc["id"]},
                    {"$set": {
                        "agent_id": env_agent_id,
                        "agent_name": env_agent_name,
                        "agent": env_agent_name,
                        "updated_at": datetime.utcnow(),
                    }},
                )
                doc["agent_id"] = env_agent_id
                doc["agent_name"] = env_agent_name
                doc["agent"] = env_agent_name

        return doc

    def _merge_live_status_dict(self, doc: Dict[str, Any]) -> Dict[str, int]:
        merged = default_live_status()
        raw = doc.get("live_status")
        if isinstance(raw, dict):
            for k in merged:
                try:
                    merged[k] = int(raw.get(k, 0) or 0)
                except (TypeError, ValueError):
                    merged[k] = 0
        return merged

    async def aggregate_live_status_from_call_history(
        self, campaign: Dict[str, Any]
    ) -> Dict[str, int]:
        counts = default_live_status()
        futwork_id = (campaign.get("futwork_campaign_id") or "").strip()
        name = (campaign.get("name") or "").strip()
        if futwork_id and name:
            match_q: Dict[str, Any] = {"$or": [{"campaign_id": futwork_id}, {"campaign": name}]}
        elif futwork_id:
            match_q = {"campaign_id": futwork_id}
        elif name:
            match_q = {"campaign": name}
        else:
            return counts

        pipeline = [
            {"$match": match_q},
            {"$project": {"fs": "$futwork_status", "st": "$status"}},
        ]
        cursor = self.db.call_history.aggregate(pipeline)
        async for row in cursor:
            key = map_stored_call_to_live_key(row.get("fs"), row.get("st"))
            if key and key in counts:
                counts[key] += 1
        return counts

    def build_current_response(
        self,
        doc: Dict[str, Any],
        live_override: Optional[Dict[str, int]] = None,
    ) -> CampaignCurrentResponse:
        live_src = live_override if live_override is not None else self._merge_live_status_dict(doc)
        disp = doc.get("dispositions")
        if not isinstance(disp, dict):
            disp = {}

        agent_id = str(doc.get("agent_id", "") or "") or (settings.FUTWORK_AGENT_ID or "").strip()
        agent_name = (
            doc.get("agent_name")
            or doc.get("agent")
            or resolve_agent_name(agent_id)
            or ""
        )

        return CampaignCurrentResponse(
            id=doc.get("id", ""),
            name=doc.get("name", "") or "",
            agent_id=agent_id,
            agent_name=agent_name,
            status=str(doc.get("status", "") or ""),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
            futwork_campaign_id=str(
                doc.get("futwork_campaign_id") or settings.FUTWORK_CAMPAIGN_ID or ""
            ),
            total_leads=int(doc.get("total_leads") or doc.get("totalLeads") or 0),
            pickup_rate=float(doc.get("pickup_rate") or doc.get("pickupRate") or 0.0),
            dispositions={str(k): int(v or 0) for k, v in disp.items()},
            live_status=LiveLeadStatus(**live_src),
            max_attempts=settings.futwork_max_attempts,
            call_rate_limit=settings.futwork_call_rate_limit,
            futwork_push_enabled=bool(
                settings.FUTWORK_API_KEY and settings.FUTWORK_CAMPAIGN_ID
            ),
        )

    async def list_upload_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        docs = (
            await self.db.lead_upload_history.find({}, {"_id": 0})
            .sort("created_at", -1)
            .to_list(length=limit)
        )
        return docs

    async def _push_one_lead_to_futwork(
        self,
        http_client: httpx.AsyncClient,
        lead: Dict[str, Any],
        *,
        campaign_id: Optional[str] = None,
    ) -> bool:
        """POST one lead to Futwork. Updates Mongo futwork_sync_status. Returns True on HTTP success."""
        ls = LeadService(self.db)
        endpoint = (
            f"https://platform.futwork.ai/api/campaigns/"
            f"{settings.FUTWORK_CAMPAIGN_ID}/leads"
        )
        headers = {
            "x-api-key": settings.FUTWORK_API_KEY,
            "Content-Type": "application/json",
        }
        raw_phone = lead.get("mobile_digits") or lead.get("mobile", "")
        db_digits = "".join(c for c in str(lead.get("mobile_digits") or "") if c.isdigit())[
            -10:
        ]

        if not (raw_phone or "").strip():
            if len(db_digits) == 10:
                await ls.apply_lead_futwork_sync(
                    mobile_digits_10=db_digits,
                    status="failed",
                    campaign_id=campaign_id,
                )
            return False

        phone = "".join(c for c in str(raw_phone) if c.isdigit())[-10:]
        match_digits = phone if len(phone) == 10 else db_digits

        if len(phone) != 10:
            logger.warning(
                "Skipping lead %s due to invalid phone: %s",
                lead.get("full_name"),
                phone,
            )
            if len(match_digits) == 10:
                await ls.apply_lead_futwork_sync(
                    mobile_digits_10=match_digits,
                    status="failed",
                    campaign_id=campaign_id,
                )
            return False

        payload = {
            "recipientPhoneNumber": phone,
            "recipientData": {
                "customer_name": lead.get("full_name", "Unknown"),
            },
        }

        try:
            response = await http_client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            try:
                body = response.json()
            except Exception:
                body = None
            futwork_lead_id = LeadService._extract_futwork_lead_id(body)
            await ls.apply_lead_futwork_sync(
                mobile_digits_10=phone,
                status="pushed",
                futwork_lead_id=futwork_lead_id if futwork_lead_id else None,
                campaign_id=campaign_id,
            )
            return True
        except httpx.HTTPStatusError as e:
            logger.error(
                "Failed to push lead %s to Futwork | HTTPStatusError: %s",
                phone,
                e,
                exc_info=True,
            )
            await ls.apply_lead_futwork_sync(
                mobile_digits_10=phone,
                status="failed",
                campaign_id=campaign_id,
            )
            return False
        except Exception as e:
            logger.error(
                "Failed to push lead %s to Futwork: %s",
                phone,
                e,
                exc_info=True,
            )
            await ls.apply_lead_futwork_sync(
                mobile_digits_10=phone,
                status="failed",
                campaign_id=campaign_id,
            )
            return False

    async def retry_failed_leads(self, campaign_id: str) -> Dict[str, Any]:
        """Re-push leads with futwork_sync_status failed for this campaign."""
        failed_leads = await self.db.leads.find(
            {"campaign_id": campaign_id, "futwork_sync_status": "failed"},
            {"_id": 0},
        ).to_list(length=10000)

        if not settings.FUTWORK_API_KEY or not settings.FUTWORK_CAMPAIGN_ID:
            logger.warning("Futwork credentials missing. Retry aborted.")
            return {
                "retried": 0,
                "succeeded": 0,
                "still_failed": len(failed_leads),
            }

        succeeded = 0
        still_failed = 0
        try:
            async with httpx.AsyncClient(timeout=30.0) as http_client:
                for lead in failed_leads:
                    ok = await self._push_one_lead_to_futwork(
                        http_client,
                        lead,
                        campaign_id=campaign_id,
                    )
                    if ok:
                        succeeded += 1
                    else:
                        still_failed += 1
        except Exception as e:
            logger.error("retry_failed_leads: unexpected error: %s", e, exc_info=True)
            raise

        return {
            "retried": len(failed_leads),
            "succeeded": succeeded,
            "still_failed": still_failed,
        }

    async def create_campaign(self, name: str, agent_id: str, audience_filters: Dict[str, Any]) -> Dict[str, Any]:
        # 1. Build Audience Query
        query = {}
        for k, v in audience_filters.items():
            if v is None or v == "all" or v == "":
                continue
            if k == "vip":
                if v:
                    query["is_vip"] = True
            elif k == "budget":
                query["budget_category"] = v
            elif k == "location":
                query["location_category"] = v
            else:
                query[k] = v

        # 2. Fetch Leads to Push
        leads_to_push = await self.db.leads.find(query, {"_id": 0}).to_list(length=5000)
        target_count = len(leads_to_push)

        if target_count == 0:
            raise ValueError("No leads found matching the selected filters")

        campaign_uuid = str(uuid.uuid4())
        lead_ids = [lid for l in leads_to_push if l.get("id")]
        if lead_ids:
            await self.db.leads.update_many(
                {"id": {"$in": lead_ids}},
                {
                    "$set": {
                        "campaign_id": campaign_uuid,
                        "futwork_sync_status": "pending",
                        "updated_at": datetime.utcnow(),
                    }
                },
            )

        # 3. Push to Futwork API (if configured)
        futwork_status = "scheduled"
        if settings.FUTWORK_API_KEY and settings.FUTWORK_CAMPAIGN_ID:
            try:
                pushed = 0
                failed = 0

                async with httpx.AsyncClient(timeout=30.0) as http_client:
                    for lead in leads_to_push:
                        ok = await self._push_one_lead_to_futwork(
                            http_client,
                            lead,
                            campaign_id=campaign_uuid,
                        )
                        if ok:
                            pushed += 1
                        else:
                            failed += 1

                logger.info(
                    "Futwork push: pushed=%s, failed=%s, campaign=%s",
                    pushed,
                    failed,
                    settings.FUTWORK_CAMPAIGN_ID,
                )
                futwork_status = "running" if pushed > 0 else "failed"
            except Exception as e:
                logger.error("Failed to push to Futwork: %s", e, exc_info=True)
                futwork_status = "failed"
        else:
            logger.warning("Futwork credentials missing in .env. Campaign saved in DB only.")

        # 4. Save Campaign Record
        agent_name = AGENT_NAME_MAP.get(agent_id, agent_id)
        campaign = {
            "id": campaign_uuid,
            "name": name,
            "agent_id": agent_id,
            "agent_name": agent_name,
            # Alias fields for frontend camelCase compatibility
            "agent": agent_name,
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "created_at": datetime.utcnow(),
            "status": futwork_status,
            "total_leads": target_count,
            "totalLeads": target_count,
            "pickup_rate": 0.0,
            "pickupRate": 0.0,
            "dispositions": {
                "interested": 0,
                "semiInterested": 0,
                "callback": 0,
                "notInterested": 0,
                "noAnswer": 0
            },
            "live_status": default_live_status(),
            "updated_at": datetime.utcnow(),
            "audience_filters": audience_filters,
            # Store Futwork's campaign ID so webhooks can match calls back
            "futwork_campaign_id": settings.FUTWORK_CAMPAIGN_ID,
        }

        await self.db.campaigns.insert_one(campaign)
        campaign.pop("_id", None)
        return campaign
