from pydantic import BaseModel
from typing import Dict

class DashboardStats(BaseModel):
    total_leads: int
    hot_leads: int
    warm_leads: int
    cold_leads: int
    interested_leads: int
    site_visits_scheduled: int
    lost_leads: int
    dormant_leads: int
    vip_pipeline: int = 0
    qualified_leads: int = 0
    lead_status_stats: Dict[str, int]
    lead_source_stats: Dict[str, int]
    regional_demand: Dict[str, int]
    budget_distribution: Dict[str, int]
