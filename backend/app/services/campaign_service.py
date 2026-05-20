import asyncio
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
from .futwork_push import post_one_lead_to_futwork

logger = logging.getLogger(__name__)

BULK_FUTWORK_PUSH_MAX_LIMIT = 5000

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
        return f"Clara Agent ({agent_id[:6]}…{agent_id[-4:]})"
    return agent_id


WHITELABEL_AGENT_DISPLAY_NAME = "Rustomjee AI Sales Agent"


def mask_futwork_agent_branding(name: Optional[str]) -> str:
    """Replace vendor-branded agent labels in API responses."""
    if name is None:
        return ""
    s = str(name).strip()
    if not s:
        return ""
    if "futwork" in s.lower():
        return WHITELABEL_AGENT_DISPLAY_NAME
    return s


class CampaignService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    @staticmethod
    def sanitize_campaign_for_response(doc: Optional[Dict[str, Any]]) -> None:
        """Mutate campaign dict so outbound JSON never exposes Futwork-branded agent names."""
        if not doc:
            return
        for key in ("agent_name", "agent"):
            if key not in doc:
                continue
            val = doc.get(key)
            if isinstance(val, str):
                doc[key] = mask_futwork_agent_branding(val)

    async def get_campaigns(self) -> List[Dict[str, Any]]:
        docs = await self.db.campaigns.find().sort("created_at", -1).to_list(length=100)
        # Remove MongoDB _id so serialization doesn't fail
        for doc in docs:
            doc.pop("_id", None)
            self.sanitize_campaign_for_response(doc)
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
        agent_name = mask_futwork_agent_branding(agent_name)

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

    _FUTWORK_HISTORY_FILTER: Dict[str, Any] = {
        "$or": [
            {"futwork_pushed": {"$gt": 0}},
            {"source": "bulk_push"},
        ]
    }

    _FUTWORK_FILTER_BATCHES_QUERY: Dict[str, Any] = {
        "$or": [
            {"futwork_pushed": {"$gt": 0}},
            {
                "source": "bulk_push",
                "status": "completed",
                "futwork_pushed": {"$gt": 0},
            },
        ]
    }

    async def list_upload_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        docs = (
            await self.db.lead_upload_history.find(self._FUTWORK_HISTORY_FILTER, {"_id": 0})
            .sort("created_at", -1)
            .to_list(length=limit)
        )
        return docs

    async def list_upload_batches_for_filters(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Futwork-synced upload batches for dashboard filter dropdowns."""
        docs = (
            await self.db.lead_upload_history.find(
                self._FUTWORK_FILTER_BATCHES_QUERY,
                {
                    "_id": 0,
                    "id": 1,
                    "batch_name": 1,
                    "filename": 1,
                    "created_at": 1,
                    "futwork_pushed": 1,
                    "processed": 1,
                },
            )
            .sort("created_at", -1)
            .to_list(length=limit)
        )
        out: List[Dict[str, Any]] = []
        for doc in docs:
            uid = doc.get("id")
            if not uid:
                continue
            pushed = int(doc.get("futwork_pushed") or 0)
            if pushed <= 0:
                continue
            name = (doc.get("batch_name") or doc.get("filename") or str(uid)).strip()
            out.append(
                {
                    "id": str(uid),
                    "name": name[:200],
                    "count": pushed,
                }
            )
        return out

    async def count_bulk_futwork_push_eligible(self) -> int:
        lead_svc = LeadService(self.db)
        return await lead_svc.count_leads_eligible_for_bulk_futwork_push()

    async def _resolve_internal_campaign_id(self) -> Optional[str]:
        try:
            doc = await self.find_campaign_by_futwork_settings()
            if doc and doc.get("id"):
                return str(doc["id"])
        except Exception:
            logger.exception("bulk_futwork_push: failed to resolve internal campaign id")
        return None

    async def _run_bulk_futwork_push(
        self,
        batch_id: str,
        batch_name: str,
        limit: int,
    ) -> None:
        lead_svc = LeadService(self.db)
        try:
            leads = await lead_svc.fetch_leads_eligible_for_bulk_futwork_push(limit)
            lead_ids = [str(l.get("id") or "") for l in leads if l.get("id")]
            if lead_ids:
                await lead_svc.tag_leads_with_upload_batch(
                    lead_ids,
                    upload_batch_id=batch_id,
                    upload_batch_name=batch_name,
                )
                for lead in leads:
                    lead["upload_batch_id"] = batch_id
                    lead["upload_batch_name"] = batch_name

            campaign_id = await self._resolve_internal_campaign_id()
            pushed, failed = await lead_svc.push_to_futwork(leads, campaign_id=campaign_id)
            attempted = len(leads)

            update: Dict[str, Any] = {
                "processed": attempted,
                "futwork_pushed": pushed,
                "futwork_failed": failed,
                "status": "completed",
            }
            if pushed <= 0 and attempted > 0:
                update["status"] = "failed"

            await self.db.lead_upload_history.update_one(
                {"id": batch_id},
                {"$set": update},
            )
            logger.info(
                "bulk_futwork_push complete | batch_id=%s | attempted=%s pushed=%s failed=%s",
                batch_id,
                attempted,
                pushed,
                failed,
            )
        except Exception:
            logger.exception("bulk_futwork_push failed | batch_id=%s", batch_id)
            await self.db.lead_upload_history.update_one(
                {"id": batch_id},
                {"$set": {"status": "failed"}},
            )

    async def start_bulk_futwork_push(self, batch_name: str, limit: int) -> Dict[str, Any]:
        if not (settings.FUTWORK_API_KEY or "").strip() or not (
            settings.FUTWORK_CAMPAIGN_ID or ""
        ).strip():
            raise ValueError("futwork_not_configured")

        lim = max(1, min(int(limit), BULK_FUTWORK_PUSH_MAX_LIMIT))
        name = (batch_name or "").strip()
        if not name:
            raise ValueError("batch_name_required")

        batch_id = str(uuid.uuid4())
        now = datetime.utcnow()
        history_doc = {
            "id": batch_id,
            "source": "bulk_push",
            "status": "processing",
            "batch_name": name[:200],
            "filename": "DB bulk push",
            "created_at": now,
            "processed": lim,
            "new_leads": 0,
            "updated_leads": 0,
            "unprocessed": 0,
            "futwork_pushed": 0,
            "futwork_failed": 0,
        }
        await self.db.lead_upload_history.insert_one(history_doc)

        asyncio.create_task(self._run_bulk_futwork_push(batch_id, name[:200], lim))

        return {
            "batch_id": batch_id,
            "status": "processing",
            "requested": lim,
        }

    async def _push_one_lead_to_futwork(
        self,
        http_client: httpx.AsyncClient,
        lead: Dict[str, Any],
        *,
        campaign_id: Optional[str] = None,
    ) -> bool:
        """POST one lead to Futwork. Updates Mongo futwork_sync_status. Returns True on HTTP success."""
        ok, _ = await post_one_lead_to_futwork(
            http_client,
            self.db,
            lead,
            campaign_id=campaign_id,
        )
        return ok

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
        agent_name = mask_futwork_agent_branding(AGENT_NAME_MAP.get(agent_id, agent_id))
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
