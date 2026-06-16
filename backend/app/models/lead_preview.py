from typing import List, Optional

from pydantic import BaseModel

from .lead import LeadDetail


class LeadTeaser(BaseModel):
    id: str
    full_name: str = "Unknown"
    project: str = ""
    location_category: str = "Other"
    budget_category: str = "Other"
    qualification_category: str = ""
    disposition: str = ""
    is_locked: bool = True


class PreviewMeta(BaseModel):
    disposition_filter: str
    unlocked_limit: int
    total_matching: int
    locked_visible: int


class VirtualCustomerPreviewResponse(BaseModel):
    unlocked: List[LeadDetail]
    locked_teasers: List[LeadTeaser]
    meta: PreviewMeta
