from __future__ import annotations

from enum import Enum
from typing import List, Optional, Union

from pydantic import BaseModel, Field, field_validator


class StructuredDisposition(str, Enum):
    hot_lead = "Hot Lead"
    semi_interested = "Semi-Interested"
    mildly_interested = "Mildly interested"
    not_interested = "Not Interested"
    voicemail = "Voicemail"
    wrong_number = "Wrong Number"
    already_bought = "Already Bought"


class StructuredConfidence(str, Enum):
    high = "High"
    medium = "Medium"
    low = "Low"


# Canonical disposition strings (unified JSON + legacy structured extraction)
UNIFIED_DISPOSITION_VALUES = (
    "Hot Lead",
    "Semi-Interested",
    "Mildly interested",
    "Not Interested",
    "Voicemail",
    "Wrong Number",
    "Already Bought",
)


class UnifiedStructuredExtraction(BaseModel):
    """
    Single JSON object from OpenAI for webhook + on-demand call summary (schema v2).
    """

    schema_version: int = Field(default=2)
    budget_match: bool = False
    budget_category: str = Field(default="Other")
    area_match: bool = False
    location_category: str = Field(default="Other")
    timeline_match: bool = False
    intent_category: str = Field(default="Other")
    disposition: str = Field(default="")
    call_summary: str = Field(default="")
    # Compatibility with batch summary + priority list
    lead_name: str = Field(default="Unknown")
    phone: str = Field(default="")
    system_tag_correct: bool = Field(default=True)
    key_signals: List[str] = Field(default_factory=list)

    @field_validator("disposition", mode="before")
    @classmethod
    def _normalize_disposition(cls, v: object) -> str:
        s = (str(v) if v is not None else "").strip()
        if not s:
            return ""
        for allowed in UNIFIED_DISPOSITION_VALUES:
            if s.lower() == allowed.lower():
                return allowed
        return "Not Interested"


class StructuredCallExtraction(BaseModel):
    lead_name: str = Field(default="Unknown")
    phone: str = Field(default="")
    recording_url: str = Field(default="")
    disposition: StructuredDisposition
    confidence: StructuredConfidence
    location_preference: str = Field(default="Not captured")
    config: str = Field(default="Not captured")
    budget: str = Field(default="Not captured")
    timeline: str = Field(default="Not captured")
    callback_agreed: bool = Field(default=False)
    whatsapp_sent: bool = Field(default=False)
    key_signals: List[str] = Field(default_factory=list)
    system_tag_correct: bool = Field(default=False)
    summary: str = Field(default="")
    next_action: Optional[str] = Field(default=None)
    exclusion_reason: Optional[str] = Field(default=None)


class BatchSummaryPayload(BaseModel):
    total_calls: int = 0
    hot_leads: int = 0
    semi_interested: int = 0
    mildly_interested: int = 0
    not_interested: int = 0
    voicemail_wrong_number: int = 0
    already_bought: int = 0
    system_tags_incorrect: int = 0
    top_priority_leads: List[str] = Field(default_factory=list)
    crm_issues_detected: List[str] = Field(default_factory=list)


class BatchSummaryObject(BaseModel):
    batch_summary: BatchSummaryPayload


StructuredOutputItem = Union[StructuredCallExtraction, BatchSummaryObject]

