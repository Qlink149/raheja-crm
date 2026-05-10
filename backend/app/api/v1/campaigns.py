import csv
import io
import logging
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from ...core.config import settings
from ...core.database import get_db
from ...models.campaign import CampaignCreate, CampaignCurrentResponse, LeadUploadHistoryEntry
from ...services.campaign_service import CampaignService

logger = logging.getLogger(__name__)
router = APIRouter()

_DOWNLOAD_FAILURE_CAP = 50000


@router.get("/current", response_model=CampaignCurrentResponse)
async def get_current_campaign(
    refresh_stats: bool = Query(
        False,
        description="If true, recompute live_status from call_history and return merged view (does not persist).",
    ),
    db=Depends(get_db),
):
    """Single campaign for dashboard, resolved via settings.FUTWORK_CAMPAIGN_ID."""
    if not (settings.FUTWORK_CAMPAIGN_ID or "").strip():
        logger.warning("get_current_campaign: FUTWORK_CAMPAIGN_ID is not set")
        raise HTTPException(
            status_code=503,
            detail="FUTWORK_CAMPAIGN_ID is not configured on the server",
        )

    service = CampaignService(db)
    try:
        doc = await service.find_campaign_by_futwork_settings()
    except Exception:
        logger.exception("get_current_campaign: database error")
        raise HTTPException(status_code=500, detail="Failed to load campaign")

    if not doc:
        raise HTTPException(
            status_code=404,
            detail="No campaign found for configured FUTWORK_CAMPAIGN_ID",
        )

    live_override = None
    if refresh_stats:
        try:
            live_override = await service.aggregate_live_status_from_call_history(doc)
        except Exception:
            logger.exception("get_current_campaign: aggregation failed")
            raise HTTPException(status_code=500, detail="Failed to refresh call statistics")

    return service.build_current_response(doc, live_override=live_override)


@router.get("/current/upload-history", response_model=List[LeadUploadHistoryEntry])
async def get_current_upload_history(
    limit: int = Query(100, ge=1, le=500),
    db=Depends(get_db),
):
    if not (settings.FUTWORK_CAMPAIGN_ID or "").strip():
        raise HTTPException(
            status_code=503,
            detail="FUTWORK_CAMPAIGN_ID is not configured on the server",
        )

    service = CampaignService(db)
    try:
        rows = await service.list_upload_history(limit=limit)
        return [LeadUploadHistoryEntry.model_validate(r) for r in rows]
    except Exception:
        logger.exception("get_current_upload_history: database error")
        raise HTTPException(status_code=500, detail="Failed to load upload history")


@router.get("/current/upload-history/{upload_id}/unprocessed.csv")
async def download_unprocessed_csv(upload_id: str, db=Depends(get_db)):
    """Stream a CSV of rows that failed to upsert during this upload.

    Columns: original CSV headers (recorded at upload time) + `error_reason`.
    """
    history = await db.lead_upload_history.find_one({"id": upload_id}, {"_id": 0})
    if not history:
        raise HTTPException(status_code=404, detail="Upload not found")

    failures = (
        await db.lead_upload_failures.find({"upload_id": upload_id}, {"_id": 0})
        .sort("row_index", 1)
        .to_list(length=_DOWNLOAD_FAILURE_CAP)
    )
    if not failures:
        raise HTTPException(status_code=404, detail="No unprocessed rows for this upload")

    headers: List[str] = list(history.get("csv_headers") or [])
    if not headers:
        # Fallback: derive from any failure row's keys, in stable order
        seen = []
        for f in failures:
            for k in (f.get("raw") or {}).keys():
                if k not in seen:
                    seen.append(k)
        headers = seen

    fieldnames = [*headers, "error_reason"]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for f in failures:
        raw = f.get("raw") or {}
        row = {k: raw.get(k, "") for k in headers}
        row["error_reason"] = f.get("reason", "")
        writer.writerow(row)
    out.seek(0)

    base = (history.get("filename") or "upload.csv")
    base = base.rsplit(".", 1)[0] or "upload"
    safe = "".join(c if (c.isalnum() or c in "._-") else "_" for c in base)
    return StreamingResponse(
        iter([out.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{safe}_unprocessed.csv"',
        },
    )


@router.get("/", response_model=List[Any])
async def list_campaigns(db=Depends(get_db)):
    service = CampaignService(db)
    return await service.get_campaigns()


@router.post("/")
async def create_campaign(payload: CampaignCreate, db=Depends(get_db)):
    service = CampaignService(db)
    try:
        result = await service.create_campaign(
            payload.name,
            payload.agent_id,
            payload.audience_filters,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/count")
async def get_audience_count(
    budget: Optional[str] = None,
    location: Optional[str] = None,
    temperature: Optional[str] = None,
    project: Optional[str] = None,
    vip_only: bool = False,
    db=Depends(get_db),
):
    query = {}
    if budget and budget != "all":
        query["budget_category"] = budget
    if location and location != "all":
        query["location_category"] = location
    if temperature and temperature != "all":
        query["temperature"] = temperature
    if project and project != "all":
        query["project"] = project
    if vip_only:
        query["is_vip"] = True

    count = await db.leads.count_documents(query)
    return {"count": count}


@router.get("/{campaign_id}/calls")
async def get_campaign_calls(campaign_id: str, db=Depends(get_db)):
    """Return all call records associated with a campaign."""
    # First find the campaign to get its name
    campaign = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    campaign_name = campaign.get("name", "")
    campaign_futwork_id = campaign.get("futwork_campaign_id", "")

    # Query call_history — match by futwork campaignId OR campaign name
    call_query: dict = {}
    if campaign_futwork_id and campaign_name:
        call_query = {"$or": [{"campaign_id": campaign_futwork_id}, {"campaign": campaign_name}]}
    elif campaign_futwork_id:
        call_query = {"campaign_id": campaign_futwork_id}
    else:
        call_query = {"campaign": campaign_name}

    calls = await db.call_history.find(
        call_query,
        {"_id": 0},
    ).sort("created_at", -1).to_list(length=500)

    # If no calls in call_history, check leads collection
    if not calls:
        leads_with_calls = await db.leads.find(
            {
                "campaign_name": campaign_name,
                "$or": [
                    {"call_status": {"$nin": ["", None]}},
                    {"disposition": {"$nin": ["", None, "New"]}},
                ],
            },
            {"_id": 0},
        ).to_list(length=500)

        calls = [
            {
                "id": l.get("lead_id", l.get("id", "")),
                "lead_id": l.get("lead_id", l.get("id", "")),
                "customer_name": l.get("full_name", "Unknown"),
                "phone": l.get("mobile", ""),
                "status": l.get("call_status", "completed"),
                "disposition": l.get("disposition", ""),
                "duration": int(l.get("call_duration", 0) or 0),
                "recording_url": l.get("recording_url", ""),
                "transcript": l.get("transcript", ""),
                "created_at": l.get("call_date", l.get("created_at", "")),
                "campaign": campaign_name,
            }
            for l in leads_with_calls
        ]

    return {"calls": calls, "campaign": campaign}
