"""Shared qualification bucket queries for dashboard stats and lead drill-down."""
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

_AI_INTERESTED = ("Hot Lead", "Semi-Interested", "Semi-interested", "Mildly interested")
_VIP_BUDGET_TIERS = ("5 Cr+", "2-5 Cr")

VALID_DASHBOARD_BUCKETS = frozenset(
    {"hot", "cold", "dormant", "qualified", "vip_pipeline"}
)


def _legacy_qualified_positive() -> Dict[str, Any]:
    return {
        "$or": [
            {"status": "Qualified"},
            {"ai_disposition": {"$in": list(_AI_INTERESTED)}},
        ]
    }


def _legacy_vip_positive() -> Dict[str, Any]:
    return {
        "$or": [
            {"is_vip": True},
            {"budget_category": {"$in": list(_VIP_BUDGET_TIERS)}},
        ]
    }


def missing_qualification_clause() -> Dict[str, Any]:
    return {
        "$or": [
            {"qualification_category": {"$exists": False}},
            {"qualification_category": None},
            {"qualification_category": ""},
        ]
    }


def qc_or_legacy(base: dict, category: str, legacy_match: Dict[str, Any]) -> dict:
    return {
        **base,
        "$or": [
            {"qualification_category": category},
            {"$and": [missing_qualification_clause(), legacy_match]},
        ],
    }


def _legacy_qualified_match() -> Dict[str, Any]:
    return {
        "$and": [
            {"status": {"$ne": "Lost"}},
            _legacy_qualified_positive(),
        ]
    }


def _legacy_vip_match() -> Dict[str, Any]:
    return {
        "$and": [
            {"status": {"$ne": "Lost"}},
            {"$nor": [_legacy_qualified_positive()]},
            _legacy_vip_positive(),
        ]
    }


def _legacy_hot_match() -> Dict[str, Any]:
    return {
        "$and": [
            {"temperature": "Hot"},
            {"status": {"$ne": "Lost"}},
            {"$nor": [_legacy_qualified_positive()]},
            {"is_vip": {"$ne": True}},
            {"budget_category": {"$nin": list(_VIP_BUDGET_TIERS)}},
        ]
    }


def _legacy_cold_match() -> Dict[str, Any]:
    return {
        "$and": [
            {"temperature": "Cold"},
            {"status": {"$ne": "Lost"}},
            {"$nor": [_legacy_qualified_positive()]},
            {"is_vip": {"$ne": True}},
            {"budget_category": {"$nin": list(_VIP_BUDGET_TIERS)}},
        ]
    }


def dormant_bucket_query(base: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **base,
        "$or": [
            {"qualification_category": "Dormant"},
            {"$and": [missing_qualification_clause(), {"status": "Lost"}]},
        ],
    }


def build_base_query(
    project: Optional[str] = None,
    days: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    base_query: Dict[str, Any] = {}
    if project and project != "all":
        base_query["project"] = project

    if days:
        cutoff = datetime.utcnow() - timedelta(days=days)
        base_query["created_at"] = {"$gte": cutoff}
    elif start_date or end_date:
        date_filter: Dict[str, Any] = {}
        if start_date:
            try:
                date_filter["$gte"] = datetime.strptime(start_date, "%Y-%m-%d")
            except ValueError:
                pass
        if end_date:
            try:
                date_filter["$lte"] = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(
                    days=1
                )
            except ValueError:
                pass
        if date_filter:
            base_query["created_at"] = date_filter
    return base_query


def bucket_query(base: Dict[str, Any], bucket: str) -> Dict[str, Any]:
    """Return Mongo match for a dashboard KPI bucket."""
    key = (bucket or "").strip().lower()
    if key == "hot":
        return {**base, "qualification_category": "Hot"}
    if key == "cold":
        return {**base, "qualification_category": "Cold"}
    if key == "dormant":
        return {**base, "qualification_category": "Dormant"}
    if key == "qualified":
        return {**base, "qualification_category": "Qualified"}
    if key == "vip_pipeline":
        return {**base, "qualification_category": "VIP Pipeline"}
    raise ValueError(f"Unknown dashboard_bucket: {bucket}")
