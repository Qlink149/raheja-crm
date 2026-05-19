import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query

from ...core.database import get_db
from ...core.security import get_current_user
from ...core.time_utils import utc_now
from ...constants.lead_kpi import (
    DEALS_CLOSED_STATUS_REGEX,
    RNR_STATUS_REGEX,
    SITE_VISIT_STATUS_REGEX,
)
from ...utils.csv_processor import normalize_agent_name

router = APIRouter()

CSV_EXPECTED_REPS = 36
_MANAGER_SUM_KEYS = (
    "total",
    "hot",
    "warm",
    "cold",
    "dormant",
    "rnr",
    "site_visits",
    "deals_closed",
    "contacted",
    "negotiation",
)

DORMANT_INACTIVITY_DAYS = 7
_INVALID_PROJECT_REGEX = {"$regex": r"^(?i)\s*(unknown|na|n/a|others|null)\s*$"}
_INVALID_REP_PATTERN = re.compile(r"^\s*(unknown|na|n/a)\s*$", re.IGNORECASE)


def _is_invalid_rep_name(name: str) -> bool:
    return bool(_INVALID_REP_PATTERN.match(name or ""))


def _stale_activity_clause(cutoff: datetime, cutoff_iso: str) -> dict:
    no_updated_dt = {"$or": [{"updated_at_dt": {"$exists": False}}, {"updated_at_dt": None}]}
    no_updated_at = {"$or": [{"updated_at": {"$exists": False}}, {"updated_at": None}]}
    return {
        "$or": [
            {"updated_at_dt": {"$lt": cutoff}},
            {
                "$and": [
                    no_updated_dt,
                    {"$or": [{"updated_at": {"$lt": cutoff}}, {"updated_at": {"$lt": cutoff_iso}}]},
                ]
            },
            {
                "$and": [
                    no_updated_dt,
                    no_updated_at,
                    {"$or": [{"created_at_dt": {"$lt": cutoff}}, {"created_at": {"$lt": cutoff_iso}}]},
                ]
            },
        ]
    }


def _non_dormant_terminal_status_clause() -> dict:
    return {
        "$nor": [
            {
                "$or": [
                    {"status": {"$regex": r"(?i)^\s*(won|lost|advance\s*paid|closed|booked|dropped|unqualified)\s*$"}},
                    {"lead_status": {"$regex": r"(?i)^\s*(won|lost|advance\s*paid|closed|booked|dropped|unqualified)\s*$"}},
                ]
            }
        ]
    }


def _dormant_leads_query(base_query: dict) -> dict:
    cutoff = utc_now() - timedelta(days=DORMANT_INACTIVITY_DAYS)
    cutoff_iso = cutoff.isoformat()
    return {"$and": [base_query, _stale_activity_clause(cutoff, cutoff_iso), _non_dormant_terminal_status_clause()]}


def _merge_query_with_valid_projects(query: dict) -> dict:
    valid_proj = {
        "project": {
            "$exists": True,
            "$nin": [None, ""],
            "$not": _INVALID_PROJECT_REGEX,
        }
    }
    if not query:
        return valid_proj
    return {"$and": [query, valid_proj]}


def _rep_name_expression() -> Dict[str, Any]:
    return {
        "$let": {
            "vars": {
                "n1": {"$toString": {"$ifNull": ["$assigned_to_name", ""]}},
                "n2": {"$toString": {"$ifNull": ["$assigned_to", ""]}},
                "n3": {"$toString": {"$ifNull": ["$presales_agent", ""]}},
            },
            "in": {
                "$cond": [
                    {"$gt": [{"$strLenCP": {"$trim": {"input": "$$n1"}}}, 0]},
                    {"$trim": {"input": "$$n1"}},
                    {
                        "$cond": [
                            {"$gt": [{"$strLenCP": {"$trim": {"input": "$$n2"}}}, 0]},
                            {"$trim": {"input": "$$n2"}},
                            {
                                "$cond": [
                                    {"$gt": [{"$strLenCP": {"$trim": {"input": "$$n3"}}}, 0]},
                                    {"$trim": {"input": "$$n3"}},
                                    "Unassigned",
                                ]
                            },
                        ]
                    },
                ]
            },
        }
    }


def _sales_metrics_stages() -> List[Dict[str, Any]]:
    rep_expr = _rep_name_expression()
    return [
        {"$addFields": {"rep": rep_expr}},
        {
            "$addFields": {
                "ls": {
                    "$toLower": {
                        "$trim": {
                            "input": {
                                "$ifNull": [
                                    "$status",
                                    {"$ifNull": ["$lead_status", ""]},
                                ]
                            }
                        }
                    }
                },
                "ofs": {"$toLower": {"$trim": {"input": {"$ifNull": ["$original_fw_status", ""]}}}},
            }
        },
        {
            "$addFields": {
                "hot": {"$cond": [{"$eq": [{"$toLower": {"$ifNull": ["$temperature", ""]}}, "hot"]}, 1, 0]},
                "warm": {"$cond": [{"$eq": [{"$toLower": {"$ifNull": ["$temperature", ""]}}, "warm"]}, 1, 0]},
                "cold": {"$cond": [{"$eq": [{"$toLower": {"$ifNull": ["$temperature", ""]}}, "cold"]}, 1, 0]},
                "rnr": {
                    "$cond": [
                        {
                            "$or": [
                                {"$eq": ["$is_rnr", True]},
                                {"$regexMatch": {"input": "$ls", "regex": RNR_STATUS_REGEX}},
                                {"$regexMatch": {"input": "$ofs", "regex": RNR_STATUS_REGEX}},
                            ]
                        },
                        1,
                        0,
                    ]
                },
                "site_visits": {
                    "$cond": [{"$regexMatch": {"input": "$ls", "regex": SITE_VISIT_STATUS_REGEX}}, 1, 0]
                },
                "deals_closed": {
                    "$cond": [
                        {"$regexMatch": {"input": "$ls", "regex": DEALS_CLOSED_STATUS_REGEX}},
                        1,
                        0,
                    ]
                },
                "contacted": {
                    "$cond": [
                        {
                            "$or": [
                                {"$gt": [{"$size": {"$ifNull": ["$context_updates", []]}}, 1]},
                                {"$gt": [{"$size": {"$ifNull": ["$status_history", []]}}, 1]},
                                {
                                    "$and": [
                                        {"$ne": [{"$ifNull": ["$last_call_date", None]}, None]},
                                        {"$ne": [{"$ifNull": ["$last_call_date", ""]}, ""]},
                                    ]
                                },
                                {
                                    "$gt": [
                                        {
                                            "$strLenCP": {
                                                "$trim": {
                                                    "input": {"$ifNull": ["$sales_qualification", ""]}
                                                }
                                            }
                                        },
                                        0,
                                    ]
                                },
                            ]
                        },
                        1,
                        0,
                    ]
                },
                "negotiation": {
                    "$cond": [{"$regexMatch": {"input": "$ls", "regex": r"^negotiation$"}}, 1, 0]
                },
                "activity_dt": {
                    "$ifNull": [
                        "$updated_at_dt",
                        {
                            "$ifNull": [
                                {
                                    "$convert": {
                                        "input": "$updated_at",
                                        "to": "date",
                                        "onError": None,
                                        "onNull": None,
                                    }
                                },
                                {
                                    "$ifNull": [
                                        "$created_at_dt",
                                        {
                                            "$convert": {
                                                "input": "$created_at",
                                                "to": "date",
                                                "onError": None,
                                                "onNull": None,
                                            }
                                        },
                                    ]
                                },
                            ]
                        },
                    ]
                },
            }
        },
    ]


def _merge_managers_by_canonical_name(
    managers: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Merge rows that share the same normalized presales agent name."""
    buckets: Dict[str, Dict[str, Any]] = {}
    collision_groups: List[Dict[str, Any]] = []

    for m in managers:
        name = str(m.get("name") or "").strip()
        if not name or name == "Unassigned" or _is_invalid_rep_name(name):
            continue
        key = normalize_agent_name(name)
        if key not in buckets:
            entry = {k: int(m.get(k) or 0) for k in _MANAGER_SUM_KEYS}
            entry["name"] = name
            entry["match_names"] = [name]
            entry["last_active"] = m.get("last_active") or ""
            entry["leads"] = []
            buckets[key] = entry
            continue

        b = buckets[key]
        for k in _MANAGER_SUM_KEYS:
            b[k] = int(b.get(k) or 0) + int(m.get(k) or 0)
        if name not in b["match_names"]:
            b["match_names"].append(name)
        if int(m.get("total") or 0) > int(b.get("total") or 0):
            b["name"] = name
        la = m.get("last_active") or ""
        if la and (not b.get("last_active") or str(la) > str(b["last_active"])):
            b["last_active"] = la

    merged: List[Dict[str, Any]] = []
    for key, b in buckets.items():
        if len(b["match_names"]) > 1:
            collision_groups.append({"canonical": key, "variants": list(b["match_names"])})
        total = int(b.get("total") or 0)
        deals = int(b.get("deals_closed") or 0)
        b["conversion_rate"] = round((deals / total) * 100) if total > 0 else 0
        merged.append(b)

    return merged, collision_groups


def _sort_and_rank_managers(managers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    assigned = [m for m in managers if m.get("name") != "Unassigned"]
    unassigned = [m for m in managers if m.get("name") == "Unassigned"]

    assigned.sort(
        key=lambda x: (
            -int(x.get("deals_closed") or 0),
            -int(x.get("site_visits") or 0),
            -int(x.get("total") or 0),
            str(x.get("name") or ""),
        )
    )
    for i, m in enumerate(assigned, start=1):
        m["rank"] = i

    if unassigned:
        for m in unassigned:
            m["rank"] = 0
        return assigned + unassigned
    return assigned


def _finalize_managers(
    managers: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], int, List[Dict[str, Any]]]:
    raw_count = sum(
        1
        for m in managers
        if m.get("name") not in (None, "Unassigned", "")
        and not _is_invalid_rep_name(str(m.get("name") or ""))
    )
    unassigned_rows = [m for m in managers if m.get("name") == "Unassigned"]
    mergeable = [
        m
        for m in managers
        if m.get("name") != "Unassigned" and not _is_invalid_rep_name(str(m.get("name") or ""))
    ]

    merged, collision_groups = _merge_managers_by_canonical_name(mergeable)
    ranked = _sort_and_rank_managers(merged + unassigned_rows)
    return ranked, raw_count, collision_groups


async def _rep_display_names_for_canonical(db, display_name: str) -> List[str]:
    """All lead rep display strings that map to the same canonical agent."""
    canonical = normalize_agent_name(display_name)
    rows = await db.leads.aggregate(
        [
            {"$addFields": {"rep": _rep_name_expression()}},
            {"$group": {"_id": "$rep"}},
        ]
    ).to_list(None)
    names: List[str] = []
    for r in rows:
        n = str(r.get("_id") or "").strip()
        if not n or n == "Unassigned" or _is_invalid_rep_name(n):
            continue
        if normalize_agent_name(n) == canonical:
            names.append(n)
    return names if names else [display_name]


async def _sales_managers_from_aggregation(db) -> tuple:
    metrics_stages = _sales_metrics_stages()
    group_stage = {
        "$group": {
            "_id": "$rep",
            "total": {"$sum": 1},
            "hot": {"$sum": "$hot"},
            "warm": {"$sum": "$warm"},
            "cold": {"$sum": "$cold"},
            "rnr": {"$sum": "$rnr"},
            "site_visits": {"$sum": "$site_visits"},
            "deals_closed": {"$sum": "$deals_closed"},
            "contacted": {"$sum": "$contacted"},
            "negotiation": {"$sum": "$negotiation"},
            "last_active": {"$max": "$activity_dt"},
        }
    }

    main_rows = await db.leads.aggregate(metrics_stages + [group_stage]).to_list(None)

    dormant_q = _dormant_leads_query({})
    dormant_rows = await db.leads.aggregate(
        [
            {"$match": dormant_q},
            {"$addFields": {"rep": _rep_name_expression()}},
            {"$group": {"_id": "$rep", "dormant": {"$sum": 1}}},
        ]
    ).to_list(None)
    dormant_by_rep = {r["_id"]: r["dormant"] for r in dormant_rows}

    managers: List[Dict[str, Any]] = []
    totals = {
        "total": 0,
        "hot": 0,
        "warm": 0,
        "cold": 0,
        "dormant": 0,
        "rnr": 0,
        "site_visits": 0,
        "deals_closed": 0,
    }

    for r in main_rows:
        name = r["_id"] or "Unassigned"
        if _is_invalid_rep_name(name):
            continue
        dcount = int(dormant_by_rep.get(name, 0))
        total = int(r.get("total", 0))
        deals = int(r.get("deals_closed", 0))
        conv = round((deals / total) * 100) if total > 0 else 0
        la = r.get("last_active")
        last_active = ""
        if isinstance(la, datetime):
            last_active = la.astimezone(timezone.utc).isoformat()
        managers.append(
            {
                "name": name,
                "total": total,
                "hot": int(r.get("hot", 0)),
                "warm": int(r.get("warm", 0)),
                "cold": int(r.get("cold", 0)),
                "dormant": dcount,
                "rnr": int(r.get("rnr", 0)),
                "site_visits": int(r.get("site_visits", 0)),
                "deals_closed": deals,
                "contacted": int(r.get("contacted", 0)),
                "negotiation": int(r.get("negotiation", 0)),
                "conversion_rate": conv,
                "last_active": last_active,
                "leads": [],
            }
        )
        totals["total"] += total
        totals["hot"] += int(r.get("hot", 0))
        totals["warm"] += int(r.get("warm", 0))
        totals["cold"] += int(r.get("cold", 0))
        totals["dormant"] += dcount
        totals["rnr"] += int(r.get("rnr", 0))
        totals["site_visits"] += int(r.get("site_visits", 0))
        totals["deals_closed"] += deals

    managers, raw_rep_count, collision_groups = _finalize_managers(managers)

    status_pipeline = [
        {
            "$addFields": {
                "status_label": {"$ifNull": ["$status", {"$ifNull": ["$lead_status", "Unknown"]}]}
            }
        },
        {"$group": {"_id": "$status_label", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 50},
    ]
    status_raw = await db.leads.aggregate(status_pipeline).to_list(50)
    by_status = [{"name": (s["_id"] or "Unknown"), "count": s["count"]} for s in status_raw]

    project_pipeline = [
        {"$match": _merge_query_with_valid_projects({})},
        {"$group": {"_id": "$project", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 50},
    ]
    proj_raw = await db.leads.aggregate(project_pipeline).to_list(50)
    by_project = [{"name": (p["_id"] or "Unknown"), "count": p["count"]} for p in proj_raw]

    return managers, totals, by_status, by_project, raw_rep_count, collision_groups


@router.get("/sales-dashboard")
async def get_sales_dashboard_analytics(
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    managers, totals, by_status, by_project, raw_rep_count, collision_groups = (
        await _sales_managers_from_aggregation(db)
    )
    users_sales_count = await db.users.count_documents(
        {"role": "sales", "is_active": True}
    )
    canonical_rep_count = sum(
        1
        for m in managers
        if m.get("name") and m.get("name") != "Unassigned" and not _is_invalid_rep_name(m["name"])
    )

    return {
        "managers": managers,
        "totals": totals,
        "by_status": by_status,
        "by_project": by_project,
        "team_meta": {
            "canonical_rep_count": canonical_rep_count,
            "active_rep_count": canonical_rep_count,
            "users_sales_count": users_sales_count,
            "distinct_rep_on_leads_raw": raw_rep_count,
            "distinct_rep_on_leads": canonical_rep_count,
            "csv_expected_reps": CSV_EXPECTED_REPS,
            "name_collision_groups": collision_groups,
            "source": "canonical_leads",
        },
    }


@router.get("/sales-dashboard/rep-leads")
async def get_sales_rep_leads(
    name: str = Query(..., min_length=1),
    skip: int = Query(0, ge=0),
    limit: int = Query(150, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    rep_expr = _rep_name_expression()
    match_names = await _rep_display_names_for_canonical(db, name)
    match_expr = {"$expr": {"$in": [rep_expr, match_names]}}
    total = await db.leads.count_documents(match_expr)

    projection = {
        "_id": 0,
        "id": 1,
        "first_name": 1,
        "last_name": 1,
        "full_name": 1,
        "project": 1,
        "temperature": 1,
        "status": 1,
        "lead_status": 1,
        "updated_at": 1,
        "created_at": 1,
        "context_updates": 1,
        "status_history": 1,
        "last_call_date": 1,
        "sales_qualification": 1,
    }
    cursor = (
        db.leads.find(match_expr, projection)
        .sort([("updated_at", -1), ("created_at", -1)])
        .skip(skip)
        .limit(limit)
    )
    leads_out: List[Dict[str, Any]] = []
    async for lead in cursor:
        cu = lead.get("context_updates") or []
        sh = lead.get("status_history") or []
        contacted_count = max(len(cu), len(sh))
        if lead.get("last_call_date") or lead.get("sales_qualification"):
            contacted_count = max(contacted_count, 1)
        leads_out.append(
            {
                "id": lead.get("id"),
                "first_name": lead.get("first_name"),
                "last_name": lead.get("last_name"),
                "full_name": lead.get("full_name"),
                "project": lead.get("project"),
                "temperature": lead.get("temperature"),
                "lead_status": lead.get("status") or lead.get("lead_status"),
                "updated_at": lead.get("updated_at"),
                "created_at": lead.get("created_at"),
                "context_updates_count": contacted_count,
            }
        )

    return {"name": name, "total": total, "skip": skip, "limit": limit, "leads": leads_out}
