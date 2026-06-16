"""Futwork call_history disposition aggregation for dashboard + AI Calling alignment."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

_IST = ZoneInfo("Asia/Kolkata")

# Case-insensitive merge for known Futwork label variants.
_DISPOSITION_CANONICAL: Dict[str, str] = {
    "incomplete conversation": "Incomplete Conversation",
    "no answer": "No Answer",
    "na": "No Answer",
    "not interested": "Not Interested",
    "partially interested": "Partially Interested",
    "interested": "Interested",
    "wrong number": "Wrong Number",
    "already bought": "Already Bought",
}

NO_DISPOSITION_LABEL = "No Disposition"


def _normalize_disposition_label(raw: Any) -> str:
    s = str(raw or "").strip()
    if not s or s.lower() == "nan":
        return NO_DISPOSITION_LABEL
    key = s.lower()
    return _DISPOSITION_CANONICAL.get(key, s)


def _ist_date_to_utc_bounds(start_date: str, end_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    try:
        day_start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=_IST)
        if end_date:
            day_end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=_IST) + timedelta(days=1)
        else:
            day_end = day_start + timedelta(days=1)
        return {
            "$gte": day_start.astimezone(timezone.utc).replace(tzinfo=None),
            "$lt": day_end.astimezone(timezone.utc).replace(tzinfo=None),
        }
    except ValueError:
        return None


def call_history_date_clause(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Build created_at filter for call_history (YYYY-MM-DD interpreted as IST days)."""
    if not start_date and not end_date:
        return None

    if start_date and not end_date:
        bounds = _ist_date_to_utc_bounds(start_date)
        return {"created_at": bounds} if bounds else None

    date_filter: Dict[str, Any] = {}
    if start_date:
        try:
            day_start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=_IST)
            date_filter["$gte"] = day_start.astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            pass
    if end_date:
        try:
            day_end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=_IST) + timedelta(days=1)
            date_filter["$lt"] = day_end.astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            pass
    if date_filter:
        return {"created_at": date_filter}
    return None


def build_call_history_match_query(
    *,
    project: Optional[str] = None,
    days: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    lead_ids: Optional[List[str]] = None,
    mobile_digits_list: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Mongo match for call_history aligned with dashboard filter params.

    Note: `days` uses UTC cutoff on call created_at (mirrors lead build_base_query).
    Custom dates use IST calendar-day bounds (mirrors AI Calling call-history APIs).
    """
    parts: List[Dict[str, Any]] = []

    if days:
        cutoff = datetime.utcnow() - timedelta(days=days)
        parts.append({"created_at": {"$gte": cutoff}})
    else:
        date_clause = call_history_date_clause(start_date, end_date)
        if date_clause:
            parts.append(date_clause)

    if lead_ids or mobile_digits_list:
        ors: List[Dict[str, Any]] = []
        if lead_ids:
            ors.append({"lead_id": {"$in": lead_ids}})
        if mobile_digits_list:
            ors.append({"mobile_digits": {"$in": mobile_digits_list}})
        if ors:
            parts.append({"$or": ors} if len(ors) > 1 else ors[0])
    elif project and project != "all":
        # Caller must pass resolved lead_ids / mobile_digits when project is set.
        parts.append({"_id": {"$exists": False}})

    if not parts:
        return {}
    if len(parts) == 1:
        return parts[0]
    return {"$and": parts}


async def resolve_project_call_correlation(
    db,
    project: str,
) -> tuple[List[str], List[str]]:
    """Return (lead_ids, mobile_digits) for leads in the given project."""
    if not project or project == "all":
        return [], []

    lead_ids: List[str] = []
    mobile_digits: List[str] = []
    cursor = db.leads.find(
        {"project": project},
        {"_id": 0, "id": 1, "mobile_digits": 1},
    )
    async for doc in cursor:
        lid = str(doc.get("id") or "").strip()
        if lid:
            lead_ids.append(lid)
        md = str(doc.get("mobile_digits") or "").strip()
        if md:
            mobile_digits.append(md)
    return lead_ids, mobile_digits


def merge_disposition_counts(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    """Normalize raw aggregation rows into {label: count}."""
    out: Dict[str, int] = {}
    for row in rows:
        label = _normalize_disposition_label(row.get("_id"))
        out[label] = out.get(label, 0) + int(row.get("count", 0) or 0)
    return out


async def aggregate_futwork_disposition_stats(
    db,
    *,
    project: Optional[str] = None,
    days: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, int]:
    """Group call_history by Futwork disposition (call-level, AI Calling source of truth)."""
    lead_ids: List[str] = []
    mobile_digits_list: List[str] = []
    if project and project != "all":
        lead_ids, mobile_digits_list = await resolve_project_call_correlation(db, project)
        if not lead_ids and not mobile_digits_list:
            return {}

    match_query = build_call_history_match_query(
        project=project,
        days=days,
        start_date=start_date,
        end_date=end_date,
        lead_ids=lead_ids or None,
        mobile_digits_list=mobile_digits_list or None,
    )

    pipeline: List[Dict[str, Any]] = []
    if match_query:
        pipeline.append({"$match": match_query})
    pipeline.extend(
        [
            {"$group": {"_id": "$disposition", "count": {"$sum": 1}}},
        ]
    )

    rows = await db.call_history.aggregate(pipeline).to_list(length=100)
    return merge_disposition_counts(rows)


def futwork_disposition_exact(value: str) -> Dict[str, Any]:
    """Exact Futwork disposition match (same logic as AI Calling disposition filter)."""
    return {
        "$or": [
            {"disposition": value},
            {"extracted_data.disposition": value},
        ]
    }


async def aggregate_avg_duration_by_disposition(
    db,
    *,
    project: Optional[str] = None,
    days: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, float]:
    """Group call_history by Futwork disposition and compute average duration."""
    lead_ids: List[str] = []
    mobile_digits_list: List[str] = []
    if project and project != "all":
        lead_ids, mobile_digits_list = await resolve_project_call_correlation(db, project)
        if not lead_ids and not mobile_digits_list:
            return {}

    match_query = build_call_history_match_query(
        project=project,
        days=days,
        start_date=start_date,
        end_date=end_date,
        lead_ids=lead_ids or None,
        mobile_digits_list=mobile_digits_list or None,
    )

    pipeline: List[Dict[str, Any]] = []
    
    # Exclude 0 duration calls to get the true "connected" average per disposition
    query_with_duration = {**match_query, "duration": {"$gt": 0}} if match_query else {"duration": {"$gt": 0}}
    pipeline.append({"$match": query_with_duration})

    pipeline.extend(
        [
            {"$group": {
                "_id": "$disposition", 
                "total_duration": {"$sum": "$duration"},
                "count": {"$sum": 1}
            }},
        ]
    )

    rows = await db.call_history.aggregate(pipeline).to_list(length=100)
    
    sums: Dict[str, float] = {}
    counts: Dict[str, int] = {}
    for row in rows:
        label = _normalize_disposition_label(row.get("_id"))
        sums[label] = sums.get(label, 0.0) + float(row.get("total_duration") or 0)
        counts[label] = counts.get(label, 0) + int(row.get("count") or 0)
        
    out: Dict[str, float] = {}
    for label in sums:
        out[label] = sums[label] / counts[label] if counts[label] > 0 else 0.0
        
    return out

