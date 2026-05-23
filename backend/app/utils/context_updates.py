"""Build and persist lead context_updates from calls and CRM fields."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..core.time_utils import serialize_datetime_utc

logger = logging.getLogger(__name__)

_SKIP_VALUES = frozenset({"", "n/a", "unknown", "0", "profiling in progress"})


def _ts_ms(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    s = str(value).strip()
    if not s:
        return None
    try:
        normalized = s if s.endswith("Z") or "+" in s[-6:] else (f"{s}Z" if "T" in s else f"{s}T00:00:00Z")
        dt = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except (TypeError, ValueError):
        return None


def _display_date(value: Any) -> str:
    ms = _ts_ms(value)
    if ms is None:
        return "—"
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return dt.strftime("%d/%m/%y")


def _has_meaningful(value: Any) -> bool:
    if value is None:
        return False
    s = str(value).strip()
    return bool(s) and s.lower() not in _SKIP_VALUES


def _duration_label(seconds: int) -> str:
    n = int(seconds or 0)
    if n <= 0:
        return ""
    mins, secs = divmod(n, 60)
    if mins > 0:
        return f" ({mins}m {secs}s)"
    return f" ({secs}s)"


def _entry(
    *,
    at: Any,
    icon: str,
    type_: str,
    context: str,
    sort_ms: Optional[int] = None,
) -> Dict[str, Any]:
    ms = sort_ms if sort_ms is not None else _ts_ms(at)
    return {
        "at": serialize_datetime_utc(at) if at else "",
        "date": _display_date(at),
        "icon": icon,
        "type": type_,
        "context": context,
        "sort_ms": ms or 0,
    }


def build_context_updates(lead: Dict[str, Any], calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build timeline entries (newest first)."""
    entries: List[Dict[str, Any]] = []
    lead = lead or {}

    call_rows = sorted(
        calls or [],
        key=lambda c: _ts_ms(c.get("created_at") or c.get("call_date")) or 0,
        reverse=True,
    )

    earliest_ms: Optional[int] = None
    for call in call_rows:
        raw_ts = call.get("created_at") or call.get("call_date")
        ms = _ts_ms(raw_ts)
        if ms is not None and (earliest_ms is None or ms < earliest_ms):
            earliest_ms = ms

        label = (call.get("disposition") or call.get("status") or "completed").strip()
        dur = int(call.get("duration", 0) or 0)
        entries.append(
            _entry(
                at=raw_ts,
                icon="phone",
                type_="call",
                context=f"Outbound call — {label}{_duration_label(dur)}",
                sort_ms=ms,
            )
        )

        se = call.get("structured_extraction")
        if isinstance(se, dict):
            summary = (se.get("call_summary") or "").strip()
            if summary:
                entries.append(
                    _entry(
                        at=raw_ts,
                        icon="human",
                        type_="human",
                        context=summary[:280],
                        sort_ms=ms,
                    )
                )

    if _has_meaningful(lead.get("sales_qualification")):
        at = lead.get("sales_qualified_at") or lead.get("updated_at")
        entries.append(
            _entry(
                at=at,
                icon="human",
                type_="human",
                context=f"Sales qualification: {lead.get('sales_qualification')}",
            )
        )

    if _has_meaningful(lead.get("budget")):
        at = lead.get("updated_at") or lead.get("last_call_date")
        entries.append(
            _entry(
                at=at,
                icon="whatsapp",
                type_="whatsapp",
                context=f"Budget: {lead.get('budget')}",
            )
        )

    if _has_meaningful(lead.get("configuration")):
        at = lead.get("updated_at") or lead.get("last_call_date")
        entries.append(
            _entry(
                at=at,
                icon="phone",
                type_="call",
                context=f"Interested in {lead.get('configuration')} configuration",
            )
        )

    if _has_meaningful(lead.get("project")):
        at = lead.get("updated_at") or lead.get("last_call_date")
        entries.append(
            _entry(
                at=at,
                icon="human",
                type_="human",
                context=f"Showed interest in {lead.get('project')}",
            )
        )

    if earliest_ms is not None:
        entries.append(
            _entry(
                at=datetime.fromtimestamp(earliest_ms / 1000, tz=timezone.utc),
                icon="phone",
                type_="call",
                context="Initial contact made",
                sort_ms=earliest_ms,
            )
        )

    if not entries:
        return [
            _entry(
                at=None,
                icon="phone",
                type_="call",
                context="Initial contact made",
                sort_ms=0,
            )
        ]

    entries.sort(key=lambda e: e.get("sort_ms", 0), reverse=True)
    seen_context: set = set()
    deduped: List[Dict[str, Any]] = []
    for e in entries:
        key = (e.get("context"), e.get("sort_ms"))
        if key in seen_context:
            continue
        seen_context.add(key)
        out = {k: v for k, v in e.items() if k != "sort_ms"}
        deduped.append(out)
    return deduped


async def fetch_calls_for_lead(db, lead_id: str) -> List[Dict[str, Any]]:
    """Load call_history rows for a lead (same logic as GET /leads/{id}/calls)."""
    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        return []

    mobile_digits = (lead.get("mobile_digits") or "").strip()
    if not mobile_digits:
        return []

    history_docs = await db.call_history.find(
        {"mobile_digits": mobile_digits},
        {"_id": 0},
    ).sort("created_at", -1).to_list(50)

    calls: List[Dict[str, Any]] = []
    for d in history_docs:
        ts = d.get("started_at") or d.get("created_at")
        se = d.get("structured_extraction") or {}
        calls.append(
            {
                "created_at": serialize_datetime_utc(ts),
                "call_date": serialize_datetime_utc(ts),
                "status": d.get("status", ""),
                "disposition": d.get("disposition", ""),
                "duration": int(d.get("duration", 0) or 0),
                "structured_extraction": se if isinstance(se, dict) else {},
            }
        )
    return calls


async def persist_lead_context_updates(db, lead_id: str) -> None:
    """Recompute and store context_updates on the lead document."""
    lead = await db.leads.find_one({"id": lead_id}, {"_id": 0})
    if not lead:
        return
    calls = await fetch_calls_for_lead(db, lead_id)
    updates = build_context_updates(lead, calls)
    await db.leads.update_one(
        {"id": lead_id},
        {"$set": {"context_updates": updates, "updated_at": datetime.now(timezone.utc)}},
    )
