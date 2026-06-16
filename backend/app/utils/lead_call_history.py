"""Resolve call_history rows that belong to a CRM lead."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from .csv_processor import normalize_phone, phone_lookup_candidates


def _ownership_clause(lead_id: str) -> Dict[str, Any]:
    return {
        "$or": [
            {"lead_id": {"$exists": False}},
            {"lead_id": None},
            {"lead_id": ""},
            {"lead_id": lead_id},
        ]
    }


def _from_number_regex(candidates: List[str]) -> str:
    alts = "|".join(re.escape(c) for c in candidates if c)
    return rf"(?:\+?91)?(?:{alts})$"


def build_lead_call_history_query(lead_id: str, lead: Dict[str, Any]) -> Dict[str, Any]:
    """
    Match calls for one lead/customer phone.

    - Always include rows explicitly linked via lead_id.
    - Outbound rows: customer phone is stored on mobile_digits.
    - Inbound rows: customer phone is usually from_number (csv_seed rows may
      incorrectly share mobile_digits across unrelated callers).
  """
    mobile_digits = normalize_phone(lead.get("mobile_digits") or lead.get("mobile") or "")
    candidates = phone_lookup_candidates(lead.get("mobile") or mobile_digits) if mobile_digits else []

    or_clauses: List[Dict[str, Any]] = [{"lead_id": lead_id}]

    if not candidates:
        return {"$or": or_clauses}

    ownership = _ownership_clause(lead_id)

    or_clauses.append(
        {
            "$and": [
                {"mobile_digits": {"$in": candidates}},
                {
                    "$or": [
                        {"direction": {"$regex": r"^outbound$", "$options": "i"}},
                        {"direction": {"$in": [None, ""]}},
                        {"direction": {"$exists": False}},
                    ]
                },
                ownership,
            ]
        }
    )

    from_regex = _from_number_regex(candidates)
    or_clauses.append(
        {
            "$and": [
                {"from_number": {"$regex": from_regex}},
                {"direction": {"$regex": r"^inbound$", "$options": "i"}},
                ownership,
            ]
        }
    )

    or_clauses.append(
        {
            "$and": [
                {"mobile_digits": {"$in": candidates}},
                {"direction": {"$regex": r"^inbound$", "$options": "i"}},
                {
                    "$or": [
                        {"from_number": {"$in": [None, ""]}},
                        {"from_number": {"$exists": False}},
                    ]
                },
                ownership,
            ]
        }
    )

    return {"$or": or_clauses}
