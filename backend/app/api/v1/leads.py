from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File
from typing import List, Optional
import logging
import re
import uuid
import pandas as pd
import io
from datetime import datetime
from ...core.config import settings
from ...core.database import get_db
from ...core.rbac import require_admin
from ...core.security import get_current_user
from ...services.lead_service import LeadService
from ...services.campaign_service import CampaignService
from ...services.assignment_service import AssignmentService, rep_lead_filter
from ...models.lead import LeadDetail

logger = logging.getLogger(__name__)
router = APIRouter()

_FAILURE_INSERT_CHUNK = 1000

SALES_QUALIFICATION_VALUES = frozenset(
    {"Cold Qualified", "Hot Lead", "VIP Pipeline"}
)


def _build_list_filters(
    *,
    budget_category=None,
    location_category=None,
    intent_category=None,
    temperature=None,
    qualification_category=None,
    project=None,
    vip_only=False,
    campaign_id=None,
    campaignId=None,
    disposition=None,
    status=None,
    assigned_user_id=None,
    assigned_rep=None,
    sales_qualification=None,
    futwork_sync_status=None,
):
    filters = {
        "budget_category": budget_category,
        "location_category": location_category,
        "intent_category": intent_category,
        "temperature": temperature,
        "qualification_category": qualification_category,
    }
    if project and project != "all":
        filters["project"] = project
    if vip_only:
        filters["is_vip"] = True
    batch_id = campaignId or None
    if batch_id:
        filters["upload_batch_id"] = batch_id
    elif campaign_id:
        filters["campaign_id"] = campaign_id
    if disposition:
        filters["disposition"] = disposition
    if status:
        filters["status"] = status
    if assigned_user_id:
        filters["assigned_user_id"] = assigned_user_id
    if sales_qualification:
        filters["sales_qualification"] = sales_qualification
    if assigned_rep:
        filters["assigned_rep"] = assigned_rep
    fw = (futwork_sync_status or "").strip().lower()
    if fw and fw != "all":
        filters["futwork_sync_status"] = futwork_sync_status
    elif not futwork_sync_status:
        filters["futwork_sync_status"] = {"$not": {"$eq": "failed"}}
    return filters


@router.get("", response_model=List[LeadDetail])
async def list_leads(
    skip: int = 0,
    limit: int = 50,
    search: Optional[str] = None,
    budget_category: Optional[str] = None,
    location_category: Optional[str] = None,
    intent_category: Optional[str] = None,
    temperature: Optional[str] = None,
    qualification_category: Optional[str] = None,
    project: Optional[str] = None,
    vip_only: bool = False,
    campaign_id: Optional[str] = None,
    campaignId: Optional[str] = None,
    disposition: Optional[str] = None,
    status: Optional[str] = None,
    assigned_user_id: Optional[str] = None,
    assigned_rep: Optional[str] = None,
    sales_qualification: Optional[str] = None,
    futwork_sync_status: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    service = LeadService(db)
    filters = _build_list_filters(
        budget_category=budget_category,
        location_category=location_category,
        intent_category=intent_category,
        temperature=temperature,
        qualification_category=qualification_category,
        project=project,
        vip_only=vip_only,
        campaign_id=campaign_id,
        campaignId=campaignId,
        disposition=disposition,
        status=status,
        assigned_user_id=assigned_user_id,
        assigned_rep=assigned_rep,
        sales_qualification=sales_qualification,
        futwork_sync_status=futwork_sync_status,
    )
    role = (current_user.get("role") or "sales").lower()
    query = service._build_leads_query(search, filters)
    if role == "sales":
        rep_filter = rep_lead_filter(current_user["id"], current_user["full_name"])
        query = {"$and": [query, rep_filter]} if query else rep_filter
        return await service.get_leads(skip, limit, None, query)

    return await service.get_leads(skip, limit, search, filters)


@router.get("/count/all")
async def get_leads_count(
    budget_category: Optional[str] = None,
    location_category: Optional[str] = None,
    intent_category: Optional[str] = None,
    temperature: Optional[str] = None,
    qualification_category: Optional[str] = None,
    project: Optional[str] = None,
    vip_only: bool = False,
    search: Optional[str] = None,
    campaign_id: Optional[str] = None,
    campaignId: Optional[str] = None,
    disposition: Optional[str] = None,
    status: Optional[str] = None,
    assigned_user_id: Optional[str] = None,
    assigned_rep: Optional[str] = None,
    sales_qualification: Optional[str] = None,
    futwork_sync_status: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    service = LeadService(db)
    filters = _build_list_filters(
        budget_category=budget_category,
        location_category=location_category,
        intent_category=intent_category,
        temperature=temperature,
        qualification_category=qualification_category,
        project=project,
        vip_only=vip_only,
        campaign_id=campaign_id,
        campaignId=campaignId,
        disposition=disposition,
        status=status,
        assigned_user_id=assigned_user_id,
        assigned_rep=assigned_rep,
        sales_qualification=sales_qualification,
        futwork_sync_status=futwork_sync_status,
    )
    role = (current_user.get("role") or "sales").lower()
    query = service._build_leads_query(search, filters)
    if role == "sales":
        rep_filter = rep_lead_filter(current_user["id"], current_user["full_name"])
        query = {"$and": [query, rep_filter]} if query else rep_filter
        count = await service.count_leads(None, query)
    else:
        count = await service.count_leads(search, filters)
    return {"count": count}


@router.delete("/clear")
async def clear_all_leads(db = Depends(get_db)):
    try:
        result = await db.leads.delete_many({})
        return {"success": True, "deleted_count": result.deleted_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error clearing leads")


@router.get("/{lead_id}", response_model=LeadDetail)
async def get_lead(lead_id: str, db = Depends(get_db)):
    service = LeadService(db)
    lead = await service.get_lead_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    # Repair alias field for frontend compatibility (non-destructive)
    try:
        await service.ensure_residential_alias(lead_id)
        lead = await service.get_lead_by_id(lead_id) or lead
    except Exception:
        logger.exception("Failed to ensure residential alias | lead_id=%s", lead_id)
    return lead


@router.get("/{lead_id}/calls")
async def get_lead_calls(lead_id: str, db = Depends(get_db)):
    """Return all call entries linked to this lead (from call_history + leads collections)."""
    # Find lead by its UUID 'id' field
    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    mobile_digits = lead.get("mobile_digits", "").strip()
    mobile = lead.get("mobile", "")

    calls = []

    # 1. Query dedicated call_history collection
    if mobile_digits:
        history_docs = await db.call_history.find(
            {"mobile_digits": mobile_digits},
            {"_id": 0}
        ).sort("created_at", -1).to_list(50)

        for d in history_docs:
            se = d.get("structured_extraction") or {}
            ai_summary = ""
            if isinstance(se, dict) and se.get("call_summary"):
                ai_summary = str(se.get("call_summary"))
            elif d.get("extracted_data"):
                ai_summary = (d.get("extracted_data") or {}).get("call_summary", "") or ""
            calls.append({
                "lead_id": lead_id,
                "call_sid": d.get("id") or d.get("call_sid") or "",
                "created_at": d.get("created_at") or d.get("started_at") or "",
                "call_date": d.get("started_at", d.get("created_at", "")),
                "status": d.get("status", ""),
                "disposition": d.get("disposition", ""),
                "duration": int(d.get("duration", 0) or 0),
                "recording_url": d.get("recording_url", ""),
                "transcript": d.get("transcript", ""),
                "ai_call_summary": ai_summary,
                "ai_worthy": d.get("ai_worthy") is not False,
                "campaign": d.get("campaign", ""),
            })

    # 2. Also check leads collection for embedded call data (from webhook upserts to leads doc)
    if not calls and mobile_digits:
        lead_call_docs = await db.leads.find(
            {
                "mobile_digits": mobile_digits,
                "$or": [
                    {"call_status": {"$nin": ["", None]}},
                    {"recording_url": {"$nin": ["", None]}},
                    {"transcript": {"$nin": ["", None]}},
                ]
            },
            {"_id": 0}
        ).sort("call_date", -1).to_list(50)

        for d in lead_call_docs:
            if not (d.get("call_status") or d.get("recording_url") or d.get("transcript")):
                continue
            calls.append({
                "lead_id": d.get("id", lead_id),
                "call_sid": "",
                "created_at": d.get("created_at") or d.get("call_date") or "",
                "call_date": d.get("call_date", d.get("created_at", "")),
                "status": d.get("call_status", ""),
                "disposition": d.get("disposition", ""),
                "duration": int(d.get("call_duration", 0) or 0),
                "recording_url": d.get("recording_url", ""),
                "transcript": d.get("transcript", ""),
                "ai_call_summary": d.get("lastCallSummary", ""),
                "ai_worthy": True,
                "campaign": d.get("campaign_name", ""),
            })

    return {"calls": calls}


def _default_batch_name(filename: Optional[str]) -> str:
    base = (filename or "upload.csv").rsplit(".", 1)[0].strip() or "upload"
    return base[:200]


@router.post("/upload")
async def upload_leads(
    file: UploadFile = File(...),
    batch_name: Optional[str] = Query(None),
    push_to_futwork: bool = Query(True),
    db = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    # ---- Size guardrail -----------------------------------------------------
    max_bytes = int(settings.LEAD_UPLOAD_MAX_BYTES or 0)
    content = await file.read()
    if max_bytes > 0 and len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"CSV is too large ({len(content)} bytes). "
                f"Maximum allowed is {max_bytes} bytes."
            ),
        )
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded CSV is empty")

    upload_id = str(uuid.uuid4())
    resolved_batch = (batch_name or "").strip() or _default_batch_name(file.filename)
    resolved_batch = re.sub(r"\s+", " ", resolved_batch).strip()[:200]

    # ---- Cloudinary raw upload (required when configured) -----------------
    original_csv_secure_url = ""
    original_csv_public_id = ""
    try:
        from ...utils.cloudinary_csv import upload_lead_csv_raw

        upload_result = await upload_lead_csv_raw(
            content,
            batch_label=resolved_batch,
            upload_id=upload_id,
        )
        original_csv_secure_url = str(upload_result.get("secure_url") or "")
        original_csv_public_id = str(upload_result.get("public_id") or "")
    except RuntimeError as e:
        logger.error("CSV storage unavailable: %s", e)
        raise HTTPException(
            status_code=503,
            detail="CSV storage is not configured. Set CLOUDINARY_URL on the server.",
        )
    except Exception as e:
        logger.exception("Cloudinary upload failed")
        raise HTTPException(
            status_code=503,
            detail=f"Could not store CSV file: {e!s}",
        )

    # ---- Parse with encoding fallback --------------------------------------
    try:
        df = pd.read_csv(io.BytesIO(content))
    except UnicodeDecodeError:
        try:
            df = pd.read_csv(io.BytesIO(content), encoding="latin-1")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid CSV encoding: {e}")
    except pd.errors.EmptyDataError:
        raise HTTPException(status_code=400, detail="CSV has no parseable rows")
    except Exception as e:
        logger.error(f"Failed to parse CSV file | Error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Invalid CSV: {e}")

    rows = df.to_dict("records")
    row_count = len(rows)
    if row_count == 0:
        raise HTTPException(status_code=400, detail="CSV contains no data rows")

    service = LeadService(db)
    result = await service.upsert_from_csv(
        rows,
        upload_batch_id=upload_id,
        upload_batch_name=resolved_batch,
        auto_assign_new=True,
    )

    processed     = int(result.get("processed", 0) or 0)
    new_count     = int(result.get("new", 0) or 0)
    updated_count = int(result.get("updated", 0) or 0)
    failed_rows   = result.get("failed_rows", []) or []
    unprocessed   = len(failed_rows)

    # ---- Persist failed rows (chunked) so they're downloadable -------------
    if failed_rows:
        try:
            failure_docs = [
                {
                    "upload_id": upload_id,
                    "row_index": int(f.get("row_index", -1)),
                    "reason": f.get("reason", ""),
                    "raw": f.get("raw", {}),
                    "created_at": datetime.utcnow(),
                }
                for f in failed_rows
            ]
            for i in range(0, len(failure_docs), _FAILURE_INSERT_CHUNK):
                await db.lead_upload_failures.insert_many(
                    failure_docs[i : i + _FAILURE_INSERT_CHUNK],
                    ordered=False,
                )
        except Exception:
            logger.exception(
                "Failed to persist lead_upload_failures | upload_id=%s | count=%s",
                upload_id,
                len(failed_rows),
            )

    pushed_count = 0
    failed_count = 0
    if push_to_futwork:
        if not (settings.FUTWORK_API_KEY or "").strip() or not (settings.FUTWORK_CAMPAIGN_ID or "").strip():
            raise HTTPException(
                status_code=503,
                detail="Futwork is not configured on the server (missing FUTWORK_API_KEY / FUTWORK_CAMPAIGN_ID).",
            )
        upload_campaign_id = None
        try:
            cs = CampaignService(db)
            doc = await cs.find_campaign_by_futwork_settings()
            if doc and doc.get("id"):
                upload_campaign_id = str(doc["id"])
        except Exception:
            logger.exception(
                "upload_leads: failed to resolve campaign for Futwork tagging",
            )
        leads_to_push = await service.leads_for_futwork_push_by_batch(upload_id)
        pushed_count, failed_count = await service.push_to_futwork(
            leads_to_push,
            campaign_id=upload_campaign_id,
        )
        result["futwork_pushed"] = pushed_count
        result["futwork_failed"] = failed_count

    # ---- History summary ---------------------------------------------------
    history_doc = {
        "id": upload_id,
        "created_at": datetime.utcnow(),
        "filename": file.filename or "upload.csv",
        "batch_name": resolved_batch,
        "original_csv_secure_url": original_csv_secure_url,
        "original_csv_public_id": original_csv_public_id,
        "processed": processed,
        "new_leads": new_count,
        "updated_leads": updated_count,
        "unprocessed": unprocessed,
        "row_count": row_count,
        "csv_headers": [str(c) for c in df.columns.tolist()],
        "futwork_pushed": pushed_count if push_to_futwork else 0,
        "futwork_failed": failed_count if push_to_futwork else 0,
    }
    if pushed_count > 0:
        try:
            await db.lead_upload_history.insert_one(history_doc)
        except Exception:
            logger.exception(
                "Failed to record lead_upload_history | upload_id=%s", upload_id
            )

    return {
        "upload_id": upload_id,
        "count": processed,
        "new": new_count,
        "updated": updated_count,
        "processed": processed,
        "unprocessed": unprocessed,
        "row_count": row_count,
        "futwork_pushed": pushed_count if push_to_futwork else 0,
        "futwork_failed": failed_count if push_to_futwork else 0,
    }


@router.patch("/{lead_id}/assign")
async def assign_lead(
    lead_id: str,
    payload: dict,
    _admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    assigned_user_id = payload.get("assigned_user_id")
    if not assigned_user_id:
        raise HTTPException(status_code=400, detail="assigned_user_id is required")
    notes = (payload.get("notes") or "").strip()
    ok = await AssignmentService(db).assign_lead(
        lead_id, assigned_user_id, transfer_notes=notes
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Lead or user not found")
    return {"status": "success", "lead_id": lead_id, "assigned_user_id": assigned_user_id}


@router.post("/{lead_id}/auto-assign")
async def auto_assign_lead(
    lead_id: str,
    _admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    rep, message = await AssignmentService(db).auto_assign_lead(lead_id)
    if not rep:
        raise HTTPException(status_code=400, detail=message)
    return {
        "status": "success",
        "assigned_to": rep.get("full_name"),
        "assigned_user_id": rep.get("id"),
        "active_leads": rep.get("active_leads", 0),
        "message": message,
    }


@router.patch("/{lead_id}/sales-qualification")
async def update_sales_qualification(
    lead_id: str,
    payload: dict,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    value = (payload.get("sales_qualification") or "").strip()
    if value and value not in SALES_QUALIFICATION_VALUES:
        raise HTTPException(
            status_code=400,
            detail=f"sales_qualification must be one of: {', '.join(sorted(SALES_QUALIFICATION_VALUES))}",
        )

    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0, "assigned_user_id": 1})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    role = (current_user.get("role") or "sales").lower()
    if role == "sales" and lead.get("assigned_user_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="You can only qualify your assigned leads")

    now = datetime.utcnow()
    await db.leads.update_one(
        {"id": lead_id},
        {
            "$set": {
                "sales_qualification": value or None,
                "sales_qualified_at": now if value else None,
                "sales_qualified_by": current_user["id"] if value else None,
                "updated_at": now,
            }
        },
    )
    return {"status": "success", "sales_qualification": value or None}


@router.patch("/{lead_id}/disposition")
async def update_disposition(lead_id: str, payload: dict, db = Depends(get_db)):
    disposition = payload.get("disposition")
    if not disposition:
        raise HTTPException(status_code=400, detail="Disposition is required")

    service = LeadService(db)
    updated = await service.update_disposition(lead_id, disposition)
    if not updated:
        raise HTTPException(status_code=404, detail="Lead not found")
    return {"status": "success", "disposition": disposition}
