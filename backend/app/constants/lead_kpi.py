"""
Shared RNR / site visit / deals-closed KPI patterns for analytics dashboards.
"""

from __future__ import annotations

import re
from typing import Optional

RNR_STATUS_REGEX = (
    r"(?i)(rnr|ring[\s\-]*no[\s\-]*response|no[\s\-]*response|"
    r"not[\s\-]*reachable|unreachable|did[\s\-]*not[\s\-]*answer|"
    r"unable[\s\-]*to[\s\-]*connect|call[\s\-]*not[\s\-]*answered)"
)

SITE_VISIT_STATUS_REGEX = r"(?i)site\s*visit"

DEALS_CLOSED_STATUS_REGEX = r"(?i)^\s*(won|advance\s*paid|closed|booked)\s*$"


def fw_status_indicates_rnr(fw_status: Optional[str]) -> bool:
    if not fw_status or not str(fw_status).strip():
        return False
    return bool(re.search(RNR_STATUS_REGEX, str(fw_status)))
