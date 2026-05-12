from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any
from datetime import datetime

class AIAgent(BaseModel):
    id: str
    name: str
    description: str
    prompt: str
    color: str

class CampaignCreate(BaseModel):
    name: str
    agent_id: str
    audience_filters: Dict[str, Any]  # Any to allow bool VIP flag

class Campaign(BaseModel):
    id: str
    name: str
    agent_id: str
    agent_name: Optional[str] = ""
    created_at: datetime
    status: str  # 'scheduled', 'running', 'completed', 'failed'
    total_leads: int
    pickup_rate: float = 0.0
    dispositions: Dict[str, int] = {
        "interested": 0,
        "semiInterested": 0,
        "callback": 0,
        "notInterested": 0,
        "noAnswer": 0
    }
    audience_filters: Dict[str, Any]

    class Config:
        extra = "allow"


class LiveLeadStatus(BaseModel):
    """Telephony-style outcome counts (Futwork status), stored under campaigns.live_status."""

    completed: int = 0
    busy: int = 0
    no_answer: int = 0
    call_disconnected: int = 0
    failed: int = 0


class CampaignCurrentResponse(BaseModel):
    """Single-campaign dashboard payload resolved via FUTWORK_CAMPAIGN_ID."""

    id: str
    name: str = ""
    agent_id: str = ""
    agent_name: Optional[str] = ""
    status: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    futwork_campaign_id: str = ""
    total_leads: int = 0
    pickup_rate: float = 0.0
    dispositions: Dict[str, int] = Field(default_factory=dict)
    live_status: LiveLeadStatus = Field(default_factory=LiveLeadStatus)
    max_attempts: Optional[int] = None
    call_rate_limit: Optional[int] = None
    # True when the server has both FUTWORK_API_KEY and FUTWORK_CAMPAIGN_ID.
    # Used by the upload modal to show/hide the "Also push to Futwork" toggle.
    futwork_push_enabled: bool = False

    class Config:
        extra = "allow"


class LeadUploadHistoryEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    created_at: datetime
    filename: str = ""
    batch_name: str = ""
    original_csv_secure_url: str = ""
    original_csv_public_id: str = ""
    processed: int = 0
    new_leads: int = 0
    updated_leads: int = 0
    unprocessed: int = 0
    futwork_pushed: int = 0
    futwork_failed: int = 0


class LeadUploadBatchRename(BaseModel):
    batch_name: str = Field(..., min_length=1, max_length=200)
