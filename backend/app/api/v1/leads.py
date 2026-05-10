from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File
from typing import List, Optional
import logging
import uuid
import pandas as pd
import io
from datetime import datetime
from ...core.config import settings
from ...core.database import get_db
from ...services.lead_service import LeadService
from ...models.lead import LeadDetail

logger = logging.getLogger(__name__)
router = APIRouter()

_FAILURE_INSERT_CHUNK = 1000

@router.get("/", response_model=List[LeadDetail])
async def list_leads(
    skip: int = 0,
    limit: int = 50,
    search: Optional[str] = None,
    budget_category: Optional[str] = None,
    location_category: Optional[str] = None,
    intent_category: Optional[str] = None,
    temperature: Optional[str] = None,
    project: Optional[str] = None,
    vip_only: bool = False,
    db = Depends(get_db)
):
    service = LeadService(db)
    filters = {
        "budget_category": budget_category,
        "location_category": location_category,
        "intent_category": intent_category,
        "temperature": temperature,
        "project": project
    }
    if vip_only:
        filters["is_vip"] = True

    return await service.get_leads(skip, limit, search, filters)


@router.get("/count/all")
async def get_leads_count(
    budget_category: Optional[str] = None,
    location_category: Optional[str] = None,
    intent_category: Optional[str] = None,
    temperature: Optional[str] = None,
    project: Optional[str] = None,
    vip_only: bool = False,
    search: Optional[str] = None,
    db = Depends(get_db)
):
    import re
    query = {}
    if budget_category and budget_category != "all": query["budget_category"] = budget_category
    if location_category and location_category != "all": query["location_category"] = location_category
    if intent_category and intent_category != "all": query["intent_category"] = intent_category
    if temperature and temperature != "all": query["temperature"] = temperature
    if project and project != "all": query["project"] = project
    if vip_only: query["is_vip"] = True

    if search:
        esc = re.escape(search)
        digits = re.sub(r"\D+", "", search)
        ors = [
            {'full_name': {'$regex': esc, '$options': 'i'}},
            {'mobile': {'$regex': esc, '$options': 'i'}},
        ]
        if digits:
            ors.append({'mobile_digits': {'$regex': digits}})
            if len(digits) > 10:
                ors.append({'mobile_digits': {'$regex': digits[-10:]}})
        query['$or'] = ors

    count = await db.leads.count_documents(query)
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
            calls.append({
                "lead_id": lead_id,
                "call_date": d.get("started_at", d.get("created_at", "")),
                "status": d.get("status", ""),
                "disposition": d.get("disposition", ""),
                "duration": int(d.get("duration", 0) or 0),
                "recording_url": d.get("recording_url", ""),
                "transcript": d.get("transcript", ""),
                "ai_call_summary": d.get("ai_call_summary", ""),
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
                "call_date": d.get("call_date", d.get("created_at", "")),
                "status": d.get("call_status", ""),
                "disposition": d.get("disposition", ""),
                "duration": int(d.get("call_duration", 0) or 0),
                "recording_url": d.get("recording_url", ""),
                "transcript": d.get("transcript", ""),
                "ai_call_summary": d.get("lastCallSummary", ""),
                "campaign": d.get("campaign_name", ""),
            })

    return {"calls": calls}


@router.post("/upload")
async def upload_leads(
    file: UploadFile = File(...),
    push_to_futwork: bool = Query(False),
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
    result = await service.upsert_from_csv(rows)

    processed     = int(result.get("processed", 0) or 0)
    new_count     = int(result.get("new", 0) or 0)
    updated_count = int(result.get("updated", 0) or 0)
    failed_rows   = result.get("failed_rows", []) or []
    unprocessed   = len(failed_rows)

    upload_id = str(uuid.uuid4())

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

    # ---- History summary ---------------------------------------------------
    history_doc = {
        "id": upload_id,
        "created_at": datetime.utcnow(),
        "filename": file.filename or "upload.csv",
        "processed": processed,
        "new_leads": new_count,
        "updated_leads": updated_count,
        "unprocessed": unprocessed,
        "row_count": row_count,
        "csv_headers": [str(c) for c in df.columns.tolist()],
    }
    try:
        await db.lead_upload_history.insert_one(history_doc)
    except Exception:
        logger.exception(
            "Failed to record lead_upload_history | upload_id=%s", upload_id
        )

    if push_to_futwork:
        from ...utils.csv_processor import process_row_to_lead
        processed_leads = [process_row_to_lead(row) for row in rows]
        pushed = await service.push_to_futwork(processed_leads)
        result["futwork_pushed"] = pushed

    return {
        "upload_id": upload_id,
        "count": processed,
        "new": new_count,
        "updated": updated_count,
        "processed": processed,
        "unprocessed": unprocessed,
        "row_count": row_count,
    }


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
