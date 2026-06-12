from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class LeadDetail(BaseModel):
    id: str
    full_name: str = "Unknown"
    mobile: str = ""
    mobile_digits: str = ""
    email: Optional[str] = ""
    project: str = ""
    location: str = ""
    source: str = ""
    status: str = "Inquiry"
    temperature: str = "Warm"
    budget: str = ""
    intent: str = ""
    location_category: str = "Other"
    budget_category: str = "Other"
    intent_category: str = "Other"
    is_hni: bool = False

    # AI Context fields from CSV
    configuration: str = ""
    current_residence_type: str = ""
    current_residence_location: str = ""
    # Alias used by frontend (extra "tial" variant)
    current_residential_location: Optional[str] = ""
    possession_requirement: Optional[str] = ""
    reason_for_purchase: Optional[str] = ""
    presales_description: Optional[str] = ""
    context_summary: Optional[str] = ""
    suggested_next_project: Optional[str] = ""
    next_action_date: Optional[str] = ""
    designation: Optional[str] = ""
    ethnicity: Optional[str] = ""
    carpet_area: Optional[str] = ""
    bhk: Optional[str] = ""
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""
    last_interaction: Optional[str] = ""

    # External correlation keys (CSV `unique_identifier`, Futwork lead id)
    external_id: Optional[str] = ""
    client_lead_id: Optional[str] = ""
    futwork_lead_id: Optional[str] = ""

    # Contact locale (presales CSV: Dialing Country / Country Code)
    country: Optional[str] = ""
    country_code: Optional[str] = ""
    phone_key: Optional[str] = ""

    # Futwork CSV/campaign push lifecycle: pending | pushed | failed
    futwork_sync_status: Optional[str] = "pending"

    # AI Summaries (GPT-4o generated + cached)
    aiPersonaSummary: Optional[str] = None
    strategicNextMove: Optional[str] = None
    lastCallSummary: Optional[str] = None

    # Migration: historical call-report lead qualification (gpt-4o-mini)
    budget_match: Optional[bool] = False
    area_match: Optional[bool] = False
    timeline_match: Optional[bool] = False
    qualification_category: Optional[str] = ""

    # Assignment (sales rep)
    assigned_user_id: Optional[str] = ""
    assigned_to: Optional[str] = ""
    assigned_to_name: Optional[str] = ""
    assigned_at: Optional[datetime] = None

    # CSV upload batch (distinct from Futwork campaign_id)
    upload_batch_id: Optional[str] = ""
    upload_batch_name: Optional[str] = ""

    # Rep qualification after call (distinct from AI qualification_category)
    sales_qualification: Optional[str] = ""
    sales_qualified_at: Optional[datetime] = None
    sales_qualified_by: Optional[str] = ""

    # Call history quick-access fields (from webhook)
    disposition: Optional[str] = "New"
    transcript: Optional[str] = ""
    last_call_date: Optional[datetime] = None
    last_call_status: Optional[str] = ""
    last_call_duration: Optional[int] = 0
    last_recording_url: Optional[str] = ""

    # Last call that produced unified structured extraction (debug / UI)
    last_structured_call_sid: Optional[str] = ""

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        extra = "allow"

class CallRecord(BaseModel):
    id: str
    lead_id: Optional[str] = None
    customer_name: Optional[str] = None
    phone: str
    mobile_digits: str = ""
    status: str
    disposition: Optional[str] = None
    duration: int = 0
    recording_url: Optional[str] = None
    transcript: Optional[str] = None
    created_at: datetime
    campaign: Optional[str] = None
    direction: str = "outbound"
    hangup_by: Optional[str] = None
    call_sid: Optional[str] = None
    is_winning: Optional[bool] = None
    teleproject: Optional[str] = None
