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
        return qc_or_legacy(base, "Hot", _legacy_hot_match())
    if key == "cold":
        return qc_or_legacy(base, "Cold", _legacy_cold_match())
    if key == "dormant":
        return dormant_bucket_query(base)
    if key == "qualified":
        return qc_or_legacy(base, "Qualified", _legacy_qualified_match())
    if key == "vip_pipeline":
        return qc_or_legacy(base, "VIP Pipeline", _legacy_vip_match())
    raise ValueError(f"Unknown dashboard_bucket: {bucket}")


def _agg_missing_qc() -> Dict[str, Any]:
    return {
        "$eq": [
            {"$trim": {"input": {"$ifNull": ["$qualification_category", ""]}}},
            "",
        ]
    }


def _agg_legacy_qualified_positive() -> Dict[str, Any]:
    return {
        "$or": [
            {"$eq": ["$status", "Qualified"]},
            {"$in": [{"$ifNull": ["$ai_disposition", ""]}, list(_AI_INTERESTED)]},
        ]
    }


def _agg_not_legacy_qualified_positive() -> Dict[str, Any]:
    return {
        "$and": [
            {"$ne": ["$status", "Qualified"]},
            {
                "$not": {
                    "$in": [{"$ifNull": ["$ai_disposition", ""]}, list(_AI_INTERESTED)]
                }
            },
        ]
    }


def _agg_legacy_vip_positive() -> Dict[str, Any]:
    return {
        "$or": [
            {"$eq": [{"$ifNull": ["$is_vip", False]}, True]},
            {"$in": [{"$ifNull": ["$budget_category", ""]}, list(_VIP_BUDGET_TIERS)]},
        ]
    }


def _agg_legacy_hot_match() -> Dict[str, Any]:
    return {
        "$and": [
            {"$eq": ["$temperature", "Hot"]},
            {"$ne": ["$status", "Lost"]},
            _agg_not_legacy_qualified_positive(),
            {"$ne": [{"$ifNull": ["$is_vip", False]}, True]},
            {
                "$not": {
                    "$in": [{"$ifNull": ["$budget_category", ""]}, list(_VIP_BUDGET_TIERS)]
                }
            },
        ]
    }


def _agg_legacy_cold_match() -> Dict[str, Any]:
    return {
        "$and": [
            {"$eq": ["$temperature", "Cold"]},
            {"$ne": ["$status", "Lost"]},
            _agg_not_legacy_qualified_positive(),
            {"$ne": [{"$ifNull": ["$is_vip", False]}, True]},
            {
                "$not": {
                    "$in": [{"$ifNull": ["$budget_category", ""]}, list(_VIP_BUDGET_TIERS)]
                }
            },
        ]
    }


def _agg_qc_or_legacy(category: str, legacy_match: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "$cond": [
            {"$eq": ["$qualification_category", category]},
            1,
            {"$cond": [{"$and": [_agg_missing_qc(), legacy_match]}, 1, 0]},
        ]
    }


def _agg_warm_match() -> Dict[str, Any]:
    return {
        "$cond": [
            {
                "$or": [
                    {"$eq": ["$temperature", "Warm"]},
                    {"$regexMatch": {"input": "$ls", "regex": r"(?i)^\s*warm\s*lead\s*$"}},
                ]
            },
            1,
            0,
        ]
    }


def _agg_dormant_match() -> Dict[str, Any]:
    return {
        "$cond": [
            {"$eq": ["$qualification_category", "Dormant"]},
            1,
            {
                "$cond": [
                    {"$and": [_agg_missing_qc(), {"$eq": ["$status", "Lost"]}]},
                    1,
                    0,
                ]
            },
        ]
    }


def sales_metrics_temperature_add_fields() -> Dict[str, Any]:
    """Per-lead 0/1 flags for sales dashboard aggregation ($addFields stage)."""
    return {
        "hot": _agg_qc_or_legacy("Hot", _agg_legacy_hot_match()),
        "warm": _agg_warm_match(),
        "cold": _agg_qc_or_legacy("Cold", _agg_legacy_cold_match()),
        "dormant": _agg_dormant_match(),
    }
